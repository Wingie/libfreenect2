#! /usr/bin/env python
"""
Kinect v2 (via Syphon) -> promap capture adapter.

On this machine the Kinect is owned by the ``KinectV2_Syphon`` openFrameworks
app (~/code/KinectV2_Syphon), which holds the USB device exclusively and
publishes three Syphon servers:

    'KinectV2 Colour'   full color stream
    'KinectV2 Depth'    512x424, depth normalized 500..5000mm -> 1..0 in shader
    'KinectV2 IR'       512x424, IR normalized

libfreenect2 needs *exclusive* USB access, so the direct pylibfreenect2 adapter
(kinect_capture.py) cannot run while that app is up -- they fight for the device.
This adapter instead reads the Kinect over Syphon, so KinectV2_Syphon stays the
single USB owner and TouchDesigner + promap both consume its feed.

For gray-code projection scanning use the COLOUR server: the camera must see the
projector's visible-light patterns (IR won't show them).

It re-implements promap's capture contract:

    get_camera_size(camera=None)   -> (width, height)
    capture(camera, width, height) -> (capture_fn, stop_fn)
        capture_fn() -> one BGR uint8 numpy frame (3-channel)
        stop_fn()    -> list of every frame captured, then stops the client

so promap_syphon_scan.py can monkeypatch promap.capture with this module.

Runtime requirements (project venv has syphon-python + pyobjc):

    source ~/code/libfreenect2/venv/bin/activate

Standalone use (no projector needed -- confirms the feed works today):

    python kinect_syphon_capture.py --list             # list live Syphon servers
    python kinect_syphon_capture.py --preview          # live colour preview
    python kinect_syphon_capture.py --preview --ir      # live IR preview
    python kinect_syphon_capture.py --preview --flip    # vertical flip if upside-down
"""

import sys
import logging

import numpy as np

from Foundation import NSRunLoop, NSDate, NSDefaultRunLoopMode
from syphon import SyphonMetalClient
from syphon.server_directory import SyphonServerDirectory
from syphon.utils.numpy import copy_mtl_texture_to_image

logger = logging.getLogger(__name__)

# Syphon server names published by KinectV2_Syphon.
SERVER_COLOUR = "KinectV2 Colour"
SERVER_IR = "KinectV2 IR"
SERVER_DEPTH = "KinectV2 Depth"

# Native published sizes.
COLOUR_SIZE = (1920, 1080)
SMALL_SIZE = (512, 424)  # depth + IR

# Module-level toggles: promap.capture's functions take no stream argument, so we
# select the source here before handing the module to promap.
USE_IR = False
FLIP_VERTICAL = False  # set True if the published texture comes in upside-down


def list_servers():
    """Return [(app_name, server_name), ...] for every live Syphon server."""
    d = SyphonServerDirectory()
    # The directory populates from run-loop notifications; pump briefly so it is
    # fully discovered before we read it.
    rl = NSRunLoop.currentRunLoop()
    for _ in range(10):
        rl.runMode_beforeDate_(NSDefaultRunLoopMode,
                               NSDate.dateWithTimeIntervalSinceNow_(0.02))
    return [(s.app_name, s.name) for s in d.servers]


def _find_description(server_name):
    d = SyphonServerDirectory()
    rl = NSRunLoop.currentRunLoop()
    for _ in range(25):
        rl.runMode_beforeDate_(NSDefaultRunLoopMode,
                               NSDate.dateWithTimeIntervalSinceNow_(0.02))
        for s in d.servers:
            if s.name == server_name:
                return s
    raise RuntimeError(
        "Syphon server {!r} not found. Is KinectV2_Syphon running? "
        "Live servers: {}".format(server_name, list_servers()))


class SyphonFrameSource:
    """Reads a Syphon server and yields the latest BGR frame.

    Syphon discovers servers and delivers frames via the *main thread's* Cocoa
    run loop, so this must live on the main thread. That is exactly where promap
    runs it: promap.project drives a Qt event loop (CFRunLoop-backed) and fires
    the capture callback from a QTimer on the main thread, which keeps Syphon
    frames flowing between patterns. read() also pumps the run loop directly so
    it works standalone (preview) too.
    """

    def __init__(self, server_name=None, flip=None):
        self.server_name = server_name or (SERVER_IR if USE_IR else SERVER_COLOUR)
        self.flip = FLIP_VERTICAL if flip is None else flip
        self._rl = NSRunLoop.currentRunLoop()
        desc = _find_description(self.server_name)
        self._client = SyphonMetalClient(desc)
        self._cur = None
        logger.info("Syphon client connected to %r", self.server_name)
        # Prime the first frame before returning.
        if self._pump_for_new_frame(timeout=10.0) is None:
            self._client.stop()
            raise RuntimeError(
                "No frame from Syphon {!r} within 10s".format(self.server_name))

    def _pump_once(self, seconds=0.005):
        self._rl.runMode_beforeDate_(
            NSDefaultRunLoopMode,
            NSDate.dateWithTimeIntervalSinceNow_(seconds))

    def _pump_for_new_frame(self, timeout=1.0):
        """Pump the run loop until a fresh frame arrives; update + return it."""
        steps = max(1, int(timeout / 0.005))
        for _ in range(steps):
            self._pump_once()
            if self._client.has_new_frame:
                rgba = copy_mtl_texture_to_image(self._client.new_frame_image)
                self._cur = self._to_bgr(rgba)
                return self._cur
        return None

    def _to_bgr(self, rgba):
        img = np.ascontiguousarray(rgba[:, :, [2, 1, 0]])  # RGBA -> BGR
        if self.flip:
            img = np.ascontiguousarray(img[::-1, :, :])
        return img

    @property
    def size(self):
        if self._cur is not None:
            h, w = self._cur.shape[:2]
            return (w, h)
        return SMALL_SIZE if USE_IR else COLOUR_SIZE

    def read(self):
        """Return the most recent frame as BGR uint8 (H, W, 3).

        Waits briefly for a fresh frame; falls back to the last one if the feed
        stalls so a single dropped frame never aborts a scan.
        """
        self._pump_for_new_frame(timeout=1.0)
        return None if self._cur is None else self._cur.copy()

    def close(self):
        self._client.stop()


# --- promap.capture-compatible module surface ---------------------------------

def get_camera_size(camera=None):
    """promap calls this to discover resolution. ``camera`` is ignored."""
    return SMALL_SIZE if USE_IR else COLOUR_SIZE


def capture(camera, width, height):
    """promap's capture contract, backed by the Kinect Syphon feed.

    Returns (capture_fn, stop_fn). capture_fn() returns one BGR frame;
    stop_fn() returns the list of all captured frames and stops the client.
    """
    src = SyphonFrameSource()
    w, h = src.size
    if (width, height) != (w, h):
        logger.warning(
            "Requested %dx%d but Syphon %r is %dx%d; using native size",
            width, height, src.server_name, w, h)

    frames = []

    def _capture():
        frame = src.read()
        frames.append(frame)
        return frame

    def _stop():
        src.close()
        return frames

    return (_capture, _stop)


# --- standalone preview / listing (works today, no projector) -----------------

def _preview(use_ir, flip):
    import cv2
    name = SERVER_IR if use_ir else SERVER_COLOUR
    src = SyphonFrameSource(server_name=name, flip=flip)
    win = "Kinect Syphon preview ({})".format(name)
    cv2.namedWindow(win, cv2.WINDOW_NORMAL)
    print("Showing live Syphon frames from {!r}. Press 'q' or Esc to quit."
          .format(name))
    try:
        while True:
            frame = src.read()
            if frame is not None:
                cv2.imshow(win, frame)
            if (cv2.waitKey(1) & 0xFF) in (ord('q'), 27):
                break
    finally:
        src.close()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO)
    p = argparse.ArgumentParser(
        description="Kinect v2 (Syphon) -> promap capture adapter")
    p.add_argument("--list", action="store_true",
                   help="List live Syphon servers and exit")
    p.add_argument("--preview", action="store_true",
                   help="Open a live preview window to confirm the feed works")
    p.add_argument("--ir", action="store_true",
                   help="Use the IR server instead of colour")
    p.add_argument("--flip", action="store_true",
                   help="Vertically flip frames (if the feed is upside-down)")
    args = p.parse_args()
    if args.list:
        for app, name in list_servers():
            print("{:20s} | {}".format(app, name))
    elif args.preview:
        _preview(args.ir, args.flip)
    else:
        p.print_help()
        sys.exit(0)
