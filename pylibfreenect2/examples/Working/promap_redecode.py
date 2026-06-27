#! /usr/bin/env python
"""
Re-run promap decode/invert/reproject on ALREADY-CAPTURED frames with a tunable
gray-code threshold -- no projector or re-scan needed.

promap's CLI does not expose decode.threshold_images' ``threshold_bw`` (the
fraction-of-peak-contrast cutoff that decides which camera pixels are "lit
enough" to decode). Lowering it recovers dimmer-lit surface area (grazing
angles, far walls) at the cost of accuracy in those dim regions. This script
monkeypatches that cutoff, then forwards everything to promap.

Usage (operate on a dir that already holds cap000.png..capNNN.png):

    # try a looser threshold, writing into a fresh dir so the original survives
    python promap_redecode.py 0.25 -dir -w scan_t025 \
        --projector-size 1920x1080 --camera-size 1920x1080 -af -v

``threshold_bw`` is the first positional arg; everything after is passed to
promap verbatim. Use -dir (decode, invert, reproject) since gray/project/capture
are already done. Point -w at the dir containing the captures.
"""

import sys
import logging


def main(argv):
    threshold_bw = float(argv[0])
    rest = argv[1:]

    import promap
    import promap.decode
    orig = promap.decode.threshold_images

    def patched(images, threshold=0.5, threshold_bw=threshold_bw):
        return orig(images, threshold=threshold, threshold_bw=threshold_bw)

    promap.decode.threshold_images = patched
    logging.getLogger(__name__).info(
        "Patched threshold_images: threshold_bw=%.3f", threshold_bw)

    sys.argv = ["promap"] + rest
    promap.main()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    main(sys.argv[1:])
