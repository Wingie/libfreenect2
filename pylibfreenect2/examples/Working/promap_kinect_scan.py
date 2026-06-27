#! /usr/bin/env python
"""
Run a promap gray-code calibration scan using the Kinect v2 as the camera.

This monkeypatches ``promap.capture`` with the Kinect adapter in
kinect_capture.py, then drives promap's normal pipeline. The projector is the
display you point promap at with ``--screen``; the Kinect watches the scene.

Prereqs:
    export DYLD_LIBRARY_PATH=~/code/libfreenect2/build/lib
    source ~/code/libfreenect2/venv/bin/activate
    pip install -e ~/code/pi-jams/tools/promap        # if not already installed

Full scan once a projector is connected (generate -> project -> capture -> decode
-> invert -> reproject, saving all intermediates into ./scan/):

    python promap_kinect_scan.py --screen "<projector display name>" \
        -w scan -af -v

Any promap CLI flags after this script's own options are passed straight through
to promap. Use --ir to scan with the Kinect IR stream instead of color.

NOTE: without a projector, promap can't project patterns. To just confirm the
Kinect feed works, run:  python kinect_capture.py --preview
"""

import sys
import logging


def main(argv):
    use_ir = "--ir" in argv
    if use_ir:
        argv = [a for a in argv if a != "--ir"]

    import kinect_capture
    kinect_capture.USE_IR = use_ir

    import promap
    import promap.capture
    # Swap promap's cv2-based capture for the Kinect-backed one. promap calls
    # these by attribute, so patching the module functions is enough.
    promap.capture.get_camera_size = kinect_capture.get_camera_size
    promap.capture.capture = kinect_capture.capture

    logging.getLogger(__name__).info(
        "Patched promap.capture -> Kinect v2 (%s stream)",
        "IR" if use_ir else "color")

    # promap.main() reads sys.argv, so hand the remaining flags to it.
    sys.argv = ["promap"] + argv
    promap.main()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main(sys.argv[1:])
