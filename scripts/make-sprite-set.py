#!/usr/bin/env python3
"""Generate a Preston Blair mouth-sprite set — a bearded smiley, drawn with ImageMagick.

This exists so you can watch the lip-sync chain work before any real mascot art is
drawn, and so a new brand has a placeholder that is obviously a placeholder.

    python3 scripts/make-sprite-set.py --out /app/portrender/brands/earl_biggers/mouths
    python3 scripts/make-sprite-set.py --out ./mouths --no-beard --skin '#9AD5E8'

Produces A.png … H.png and X.png. Real art replaces these file-for-file; nothing else
in the chain changes. See docs/render-pipeline.md for what each shape means.

Implementation note: the beard is a circular *segment* of the head — an arc path
following the head's own circle between the ends of a horizontal chord — so it can
never spill outside the face. A rectangle mask leaves square corners; an alpha
CopyOpacity composite flattens the head's transparency to black. Both were tried.
"""
from __future__ import annotations

import argparse
import math
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SIZE = 768
CX = CY = SIZE // 2
HEAD_R = 300
MOUTH_CY = CY + 90

# shape -> (half-width, half-height, extra detail)
SHAPES: dict[str, tuple[int, int, str]] = {
    "A": (78,   7, "plain"),     # closed          M B P
    "B": (88,  30, "plain"),     # slight open     most consonants
    "C": (104, 62, "plain"),     # open            E
    "D": (108, 96, "plain"),     # wide open       AI / "aa"
    "E": (64,  58, "plain"),     # rounded         O
    "F": (44,  40, "plain"),     # puckered        U W
    "G": (92,  26, "teeth"),     # teeth on lip    F V
    "H": (96,  54, "tongue"),    # tongue up       L
    "X": (64,   6, "plain"),     # rest            silence
}


def _run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True, capture_output=True)


def build_face(work: Path, *, skin: str, beard: bool) -> Path:
    """Head + beard + eyes + brows. Everything except the mouth.

    The beard is a circular *segment* of the head — a path that follows the head's own
    arc between the two ends of a horizontal chord — so it cannot spill outside the
    face. The obvious alternatives both fail: a rectangle mask leaves square corners,
    and an alpha CopyOpacity composite flattens the head's own transparency to black.
    """
    head = work / "head.png"
    _run(["convert", "-size", f"{SIZE}x{SIZE}", "xc:none",
          "-fill", skin, "-stroke", "#8A6A3B", "-strokewidth", "8",
          "-draw", f"circle {CX},{CY} {CX},{CY - HEAD_R}", str(head)])

    cmd = ["convert", str(head)]
    if beard:
        chord_y = CY + 25                       # where the beard line sits
        d = chord_y - CY
        half = math.sqrt(HEAD_R ** 2 - d ** 2)  # chord half-width on the head circle
        x0, x1 = CX - half, CX + half
        # Going left -> right, sweep-flag 0 is the LOWER arc (the chin). Flag 1 puts
        # the beard on the forehead, which is a funnier bug than it is a useful one.
        seg = (f"path 'M {x0:.1f},{chord_y} "
               f"A {HEAD_R},{HEAD_R} 0 0,0 {x1:.1f},{chord_y} Z'")
        cmd += ["-fill", "#4A3522", "-stroke", "none", "-draw", seg,
                # moustache, so the mouth reads as sitting inside facial hair
                "-draw", f"ellipse {CX},{MOUTH_CY - 56} 110,30 0,360",
                # rim last, so the beard never covers the outline
                "-fill", "none", "-stroke", "#8A6A3B", "-strokewidth", "8",
                "-draw", f"circle {CX},{CY} {CX},{CY - HEAD_R}"]

    cmd += ["-fill", "#2E2E2E", "-stroke", "none",
            "-draw", f"ellipse {CX - 96},{CY - 90} 26,32 0,360",
            "-draw", f"ellipse {CX + 96},{CY - 90} 26,32 0,360",
            "-fill", "none", "-stroke", "#4A3522", "-strokewidth", "14",
            "-draw", f"arc {CX - 142},{CY - 186} {CX - 50},{CY - 106} 200,340",
            "-draw", f"arc {CX + 50},{CY - 186} {CX + 142},{CY - 106} 200,340",
            str(head)]
    _run(cmd)
    return head


def draw_mouth(face: Path, letter: str, dst: Path, *, label: bool) -> None:
    hw, hh, kind = SHAPES[letter]
    cmd = ["convert", str(face),
           "-fill", "#6E1F1F", "-stroke", "#2A0E0E", "-strokewidth", "6",
           "-draw", f"ellipse {CX},{MOUTH_CY} {hw},{max(hh, 4)} 0,360"]
    if kind == "teeth":
        cmd += ["-fill", "#FFFFFF", "-stroke", "none",
                "-draw", f"roundrectangle {CX - hw + 14},{MOUTH_CY - hh + 2} "
                         f"{CX + hw - 14},{MOUTH_CY - hh + 16} 4,4"]
    elif kind == "tongue":
        cmd += ["-fill", "#C4566B", "-stroke", "none",
                "-draw", f"ellipse {CX},{MOUTH_CY + hh // 3} {hw // 2},{hh // 3} 0,360"]
    if label:
        cmd += ["-fill", "#2E2E2E", "-stroke", "none", "-pointsize", "40",
                "-gravity", "north", "-annotate", "+0+22", letter]
    cmd.append(str(dst))
    _run(cmd)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True, help="directory to write A.png … X.png into")
    ap.add_argument("--skin", default="#F2C89B")
    ap.add_argument("--no-beard", dest="beard", action="store_false")
    ap.add_argument("--no-label", dest="label", action="store_false",
                    help="omit the shape letter (on by default: these are placeholders)")
    args = ap.parse_args()

    if not shutil.which("convert"):
        print("ImageMagick `convert` not found (sudo apt install imagemagick)",
              file=sys.stderr)
        return 2

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        face = build_face(Path(tmp), skin=args.skin, beard=args.beard)
        for letter in SHAPES:
            draw_mouth(face, letter, out_dir / f"{letter}.png", label=args.label)
    print(f"wrote {len(SHAPES)} sprites to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
