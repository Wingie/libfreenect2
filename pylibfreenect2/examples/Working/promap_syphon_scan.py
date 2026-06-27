#! /usr/bin/env python
"""
Run a promap gray-code calibration scan using the Kinect v2 *via Syphon*.

Unlike promap_kinect_scan.py (which opens libfreenect2 directly and so cannot
coexist with the running KinectV2_Syphon app), this reads the Kinect over Syphon
through kinect_syphon_capture.py. KinectV2_Syphon stays the single USB owner;
promap just consumes its 'KinectV2 Colour' feed.

This monkeypatches ``promap.capture`` with the Syphon adapter, then drives
promap's normal pipeline. The projector is the display promap projects patterns
onto; the Kinect (via Syphon) watches the scene.

Prereqs:
    source ~/code/libfreenect2/venv/bin/activate
    pip install -e ~/code/pi-jams/tools/promap        # if not already installed
    # KinectV2_Syphon.app must be running (publishes the Syphon servers)

Full scan once the projector is showing patterns (generate -> project -> capture
-> decode -> invert -> reproject, saving all intermediates into ./scan/):

    python promap_syphon_scan.py -w scan -af -v

promap picks the last screen as the projector by default; pass --screen to force
one. Any promap CLI flags after this script's own options pass straight through.

Notes:
  * Use the COLOUR feed (default). --ir is accepted but IR will NOT see the
    projector's visible-light patterns, so gray-code decoding fails -- it exists
    only for debugging the capture path.
  * --flip vertically flips frames if the Syphon feed comes in upside-down
    (check first with: python kinect_syphon_capture.py --preview).
"""

import sys
import logging


def _install_projector_placement():
    """Make promap project onto the external projector reliably on macOS.

    promap.project.project() does win.show() (lands on the main display) then
    setScreen()+showFullScreen(). With macOS "Displays have separate Spaces",
    native fullscreen ignores the re-parent and stays on the laptop. We replace
    project() with a version that uses a frameless borderless window pinned to
    the projector's exact geometry, and pick the projector by geometry (the
    non-primary screen) since both screens report empty names here.
    """
    import promap.project as P
    from PyQt5.QtCore import QTimer, Qt
    from PyQt5.QtGui import QImage, QPixmap
    from PyQt5.QtWidgets import QWidget, QLabel, QGridLayout, QApplication

    def pick_projector(screen_name=None):
        # Enumerate via the same run-loop dance promap uses.
        s_primary = QApplication.primaryScreen()
        screens = QApplication.screens()
        if not screens:
            raise P.ProjectError("Could not enumerate screens")
        externals = [s for s in screens if s is not s_primary]
        if externals:
            # Prefer a 1920x1080 external if there are several.
            for s in externals:
                if (s.geometry().width(), s.geometry().height()) == (1920, 1080):
                    return s
            return externals[-1]
        return screens[-1]

    def project(images, startup_delay=5, period=2, screen_name=None,
                capture_callback=None):
        logger = logging.getLogger("promap.project")
        s = pick_projector(screen_name)
        g = s.geometry()
        logger.info("Projecting onto screen at %d,%d %dx%d",
                    g.x(), g.y(), g.width(), g.height())

        win = QWidget()
        win.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        win.setGeometry(g)
        win.show()
        win.windowHandle().setScreen(s)
        win.setGeometry(g)
        win.move(g.topLeft())
        win.raise_()

        layout = QGridLayout()
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)
        win.setLayout(layout)
        l = QLabel(win)
        layout.addWidget(l)
        l.show()

        def show_image(im):
            i = QImage(im.data, im.shape[1], im.shape[0],
                       QImage.Format_Grayscale8)
            pm = QPixmap()
            pm.convertFromImage(i)
            l.setPixmap(pm)

        t = QTimer()
        current_image = -1

        def advance():
            nonlocal current_image
            if current_image >= 0 and capture_callback is not None:
                capture_callback()
            current_image += 1
            if current_image >= len(images):
                P.app.quit()
                return
            show_image(images[current_image])
            logger.info("Showing image {}".format(current_image))
            t.start(int(period * 1000))

        t.timeout.connect(advance)
        t.setSingleShot(True)
        t.start(int(startup_delay * 1000))
        show_image(images[-1])  # neutral-ish frame so the camera can stabilize
        logger.info("Showing last image so camera can stabilize")
        P.app.exec()

    P.get_screen = pick_projector
    P.project = project
    # promap imported project into its namespace already; repoint that too.
    import promap
    if hasattr(promap, "project") and hasattr(promap.project, "project"):
        promap.project.project = project


def main(argv):
    use_ir = "--ir" in argv
    flip = "--flip" in argv
    argv = [a for a in argv if a not in ("--ir", "--flip")]

    import kinect_syphon_capture
    kinect_syphon_capture.USE_IR = use_ir
    kinect_syphon_capture.FLIP_VERTICAL = flip

    import promap
    import promap.capture
    # Swap promap's cv2-based capture for the Syphon-backed one. promap calls
    # these by attribute, so patching the module functions is enough.
    promap.capture.get_camera_size = kinect_syphon_capture.get_camera_size
    promap.capture.capture = kinect_syphon_capture.capture

    _install_projector_placement()

    logger = logging.getLogger(__name__)
    logger.info("Patched promap.capture -> Kinect v2 Syphon (%s feed%s)",
                "IR" if use_ir else "colour", ", flipped" if flip else "")
    if use_ir:
        logger.warning("IR feed cannot see projected visible-light patterns; "
                       "gray-code decode will fail. Use colour for real scans.")

    # promap.main() reads sys.argv, so hand the remaining flags to it.
    sys.argv = ["promap"] + argv
    promap.main()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main(sys.argv[1:])
