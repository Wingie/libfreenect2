#! /usr/bin/env python
"""
Kinect v2 -> promap capture adapter.

promap (~/code/pi-jams/tools/promap) captures gray-code scans through its
``promap.capture`` module, which opens cameras with ``cv2.VideoCapture``.
pylibfreenect2 frames are NOT cv2-openable, so we can't pass the Kinect via
promap's ``--camera`` flag. Instead this module re-implements promap's capture
contract on top of pylibfreenect2:

    get_camera_size(camera=None)        -> (width, height)
    capture(camera, width, height)      -> (capture_fn, stop_fn)
        capture_fn()  -> one BGR uint8 numpy frame (3-channel)
        stop_fn()     -> list of every frame captured, then releases the device

That is exactly the surface promap.capture exposes, so promap_kinect_scan.py
can monkeypatch promap.capture with this module and run the real pipeline.

Runtime requirements (the dylib is not on the default search path):

    export DYLD_LIBRARY_PATH=~/code/libfreenect2/build/lib
    source ~/code/libfreenect2/venv/bin/activate

Standalone use (no projector needed -- confirms the Kinect feeds frames today):

    python kinect_capture.py --preview          # live color preview window
    python kinect_capture.py --preview --ir      # live IR preview (gray-code friendly)
"""

import sys
import logging

import numpy as np

from pylibfreenect2 import Freenect2, SyncMultiFrameListener, FrameType

logger = logging.getLogger(__name__)

# Kinect v2 native stream sizes.
COLOR_SIZE = (1920, 1080)
IR_SIZE = (512, 424)

# Module-level toggle: promap.capture's functions take no stream argument, so we
# select color vs IR here before handing the module to promap.
USE_IR = False


def _select_pipeline():
    """Pick the fastest available depth pipeline, matching the other examples."""
    try:
        from pylibfreenect2 import OpenGLPacketPipeline
        return OpenGLPacketPipeline()
    except ImportError:
        pass
    try:
        from pylibfreenect2 import OpenCLPacketPipeline
        return OpenCLPacketPipeline()
    except ImportError:
        from pylibfreenect2 import CpuPacketPipeline
        return CpuPacketPipeline()


class KinectSource:
    """Owns the Freenect2 device + listener lifecycle and yields BGR frames."""

    def __init__(self, use_ir=None):
        self.use_ir = USE_IR if use_ir is None else use_ir
        self._fn = Freenect2()
        if self._fn.enumerateDevices() == 0:
            raise RuntimeError(
                "No Kinect v2 connected. Check USB 3.0 + power, and that "
                "DYLD_LIBRARY_PATH points at build/lib.")
        serial = self._fn.getDeviceSerialNumber(0)
        self._device = self._fn.openDevice(serial, pipeline=_select_pipeline())

        types = FrameType.Ir if self.use_ir else FrameType.Color
        # IR frames only arrive together with depth on this listener.
        if self.use_ir:
            types = FrameType.Ir | FrameType.Depth
        self._listener = SyncMultiFrameListener(types)
        if self.use_ir:
            self._device.setIrAndDepthFrameListener(self._listener)
        else:
            self._device.setColorFrameListener(self._listener)
        self._device.start()
        logger.info("Kinect %s started (%s stream)", serial,
                    "IR" if self.use_ir else "color")

    @property
    def size(self):
        return IR_SIZE if self.use_ir else COLOR_SIZE

    def read(self):
        """Block for the next frame and return it as BGR uint8 (H, W, 3)."""
        frames = self._listener.waitForNewFrame()
        try:
            if self.use_ir:
                ir = frames["ir"].asarray(np.float32)  # 0..65535
                norm = np.clip(ir / 256.0, 0, 255).astype(np.uint8)
                bgr = np.repeat(norm[:, :, None], 3, axis=2)
            else:
                color = frames["color"].asarray()       # BGRX, uint8
                bgr = np.ascontiguousarray(color[:, :, :3])
            return bgr
        finally:
            self._listener.release(frames)

    def close(self):
        try:
            self._device.stop()
        finally:
            self._device.close()


# --- promap.capture-compatible module surface ---------------------------------

def get_camera_size(camera=None):
    """promap calls this to discover resolution. ``camera`` is ignored."""
    return IR_SIZE if USE_IR else COLOR_SIZE


def capture(camera, width, height):
    """promap's capture contract, backed by the Kinect.

    Returns (capture_fn, stop_fn). capture_fn() returns one BGR frame;
    stop_fn() returns the list of all captured frames and releases the device.
    """
    src = KinectSource()
    w, h = src.size
    if (width, height) != (w, h):
        logger.warning(
            "Requested %dx%d but Kinect %s stream is %dx%d; using native size",
            width, height, "IR" if USE_IR else "color", w, h)

    frames = []

    def _capture():
        frame = src.read()
        frames.append(frame)
        return frame

    def _stop():
        src.close()
        return frames

    return (_capture, _stop)


# --- standalone preview (works today, no projector) ---------------------------

def _preview(use_ir):
    import cv2
    src = KinectSource(use_ir=use_ir)
    win = "Kinect capture preview ({})".format("IR" if use_ir else "color")
    cv2.namedWindow(win, cv2.WINDOW_NORMAL)
    print("Showing live Kinect frames. Press 'q' or Esc to quit.")
    try:
        while True:
            frame = src.read()
            cv2.imshow(win, frame)
            key = cv2.waitKey(1) & 0xFF
            if key in (ord('q'), 27):
                break
    finally:
        src.close()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO)
    p = argparse.ArgumentParser(description="Kinect v2 -> promap capture adapter")
    p.add_argument("--preview", action="store_true",
                   help="Open a live preview window to confirm the Kinect works")
    p.add_argument("--ir", action="store_true",
                   help="Use the IR stream instead of color (better for gray codes)")
    args = p.parse_args()
    if args.preview:
        _preview(args.ir)
    else:
        p.print_help()
        sys.exit(0)
