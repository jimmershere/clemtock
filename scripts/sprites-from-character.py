#!/usr/bin/env python3
"""Turn ONE character picture into the nine mouth sprites the avatar chain needs.

You have a drawing of your character. The lip-sync pipeline needs the same drawing nine
times, differing only in the mouth. This does that: it paints each Preston Blair mouth
shape over the character at a spot you point it at.

Two steps, because guessing where a mouth is on an arbitrary drawing does not work:

    # 1. Find the mouth. Writes ONE preview with a box drawn on it. Look at it, adjust, repeat.
    python3 scripts/sprites-from-character.py --image jimmer.png --calibrate \\
        --mouth-x 0.50 --mouth-y 0.62 --mouth-w 0.12

    # 2. Happy with the box? Generate the set.
    python3 scripts/sprites-from-character.py --image jimmer.png \\
        --mouth-x 0.50 --mouth-y 0.62 --mouth-w 0.12 \\
        --out /app/portrender/brands/<slug>/mouths

Coordinates are FRACTIONS of the image (0.5 = halfway across), so they survive resizing
and you can reuse the same numbers for a re-export of the same character.

This is a serviceable shortcut, not real animation. A character drawn once and re-drawn
per mouth shape by an artist will always look better — this exists so a client's mascot
works the same day they send a picture. Deliberately no face detection: it fails on
stylised art exactly when you need it, and a wrong box is worse than one you set yourself.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

# shape -> (width multiple, height multiple, detail). Multiples of the mouth width you give.
SHAPES: dict[str, tuple[float, float, str]] = {
    "A": (1.00, 0.07, "plain"),    # closed        M B P
    "B": (1.05, 0.30, "plain"),    # slight open   most consonants
    "C": (1.15, 0.60, "plain"),    # open          E
    "D": (1.20, 0.95, "plain"),    # wide open     "aa" AI
    "E": (0.72, 0.58, "plain"),    # rounded       O
    "F": (0.50, 0.40, "plain"),    # puckered      U W
    "G": (1.05, 0.26, "teeth"),    # teeth on lip  F V
    "H": (1.10, 0.55, "tongue"),   # tongue up     L
    "X": (0.80, 0.06, "plain"),    # rest          silence
}


def _run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True, capture_output=True)


def _mouth_draw_ops(letter: str, cx: int, cy: int, mw: int,
                    fill: str, stroke: str) -> list[str]:
    wm, hm, kind = SHAPES[letter]
    hw = max(int(mw * wm / 2), 2)
    hh = max(int(mw * hm / 2), 2)
    ops = ["-fill", fill, "-stroke", stroke, "-strokewidth", str(max(mw // 24, 2)),
           "-draw", f"ellipse {cx},{cy} {hw},{hh} 0,360"]
    if kind == "teeth":
        ops += ["-fill", "#FFFFFF", "-stroke", "none",
                "-draw", f"rectangle {cx-hw+max(hw//8,2)},{cy-hh+2} "
                         f"{cx+hw-max(hw//8,2)},{cy-hh+max(hh//2,3)}"]
    elif kind == "tongue":
        ops += ["-fill", "#C4566B", "-stroke", "none",
                "-draw", f"ellipse {cx},{cy+hh//3} {hw//2},{max(hh//3,2)} 0,360"]
    return ops


def sample_skin(img: Path, cx: int, cy: int, mw: float) -> str:
    """Find the character's skin tone near the mouth, robustly.

    Sampling a single point above the mouth is what you reach for first and it is wrong:
    on jimmer that lands on the upper lip (fine), on michael it lands on his SUNGLASSES
    and returns near-black, which paints a dark blob over his face. So sample a ring of
    candidates, throw out anything too dark or too desaturated to be skin (hair, glasses,
    shadow, beard), and take the median of what survives.
    """
    pts = [(cx - 2.0 * mw, cy - 0.6 * mw), (cx + 2.0 * mw, cy - 0.6 * mw),   # cheeks
           (cx - 1.8 * mw, cy + 0.9 * mw), (cx + 1.8 * mw, cy + 0.9 * mw),   # jaw
           (cx,            cy - 1.6 * mw),                                   # philtrum/nose
           (cx - 2.4 * mw, cy),            (cx + 2.4 * mw, cy)]
    good: list[tuple[int, int, int]] = []
    for px, py in pts:
        hexv = sample_color(img, max(int(px), 0), max(int(py), 0))
        r, g, b = (int(hexv[i:i + 2], 16) for i in (1, 3, 5))
        luma = 0.299 * r + 0.587 * g + 0.114 * b
        if luma < 70:                 # glasses, hair, shadow
            continue
        if max(r, g, b) - min(r, g, b) < 12 and luma < 150:   # flat grey, not skin
            continue
        if r < g or r < b:            # skin is red-dominant in every palette we have
            continue
        good.append((r, g, b))
    if not good:
        return "#D9A177"              # a plain mid skin tone beats a black blob
    good.sort(key=lambda c: 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2])
    r, g, b = good[len(good) // 2]
    return f"#{r:02X}{g:02X}{b:02X}"


def sample_color(img: Path, x: int, y: int) -> str:
    """Hex colour of one pixel."""
    # ImageMagick's format string is full of % escapes, so build it without %-formatting.
    fmt = "%[hex:p{" + str(x) + "," + str(y) + "}]"
    out = subprocess.run(["convert", str(img), "-format", fmt, "info:"],
                         check=True, capture_output=True).stdout.decode().strip()
    return "#" + out[:6]


def _cover_ops(cx: int, cy: int, mw: int, color: str, scale: float) -> list[str]:
    """Paint out the mouth the artist already drew.

    Without this the new mouth is drawn *on top of* the existing smile and the two fight:
    a wide drawn grin still reads through a small 'closed' shape, and a large 'open' shape
    just looks like a hole punched in the face. Covering first gives every shape a clean
    patch of skin to sit on.
    """
    hw = max(int(mw * scale / 2), 3)
    hh = max(int(mw * scale * 0.42 / 2), 3)
    return ["-fill", color, "-stroke", "none",
            "-draw", f"ellipse {cx},{cy} {hw},{hh} 0,360"]


def _draw_feathered(img: Path, dst: Path, *, cx: int, cy: int, mw: int, letter: str,
                    fill: str, stroke: str, feather: float,
                    cover: tuple[str, float] | None = None) -> None:
    """Blend the mouth in instead of stamping it on.

    A hard-edged ellipse looks like a sticker on anything more detailed than flat cartoon
    art. Drawing the mouth on its own transparent layer, blurring that layer's edge, and
    compositing it back reads as part of the face instead of on top of it.
    """
    import tempfile
    w, h = dimensions(img)
    radius = max(mw * feather, 0.6)
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp) / "base.png"
        if cover:
            colour, scale = cover
            # The cover patch is feathered too, or its own edge becomes the artefact.
            patch = Path(tmp) / "patch.png"
            _run(["convert", "-size", f"{w}x{h}", "xc:none",
                  *_cover_ops(cx, cy, mw, colour, scale),
                  "-channel", "A", "-blur", f"0x{max(mw*0.05,0.6):.2f}", "+channel", str(patch)])
            _run(["convert", str(img), str(patch), "-compose", "over", "-composite", str(base)])
        else:
            shutil.copy(img, base)
        layer = Path(tmp) / "mouth.png"
        _run(["convert", "-size", f"{w}x{h}", "xc:none",
              *_mouth_draw_ops(letter, cx, cy, mw, fill, stroke),
              "-channel", "A", "-blur", f"0x{radius:.2f}", "+channel", str(layer)])
        _run(["convert", str(base), str(layer), "-compose", "over", "-composite", str(dst)])


def dimensions(img: Path) -> tuple[int, int]:
    out = subprocess.run(["identify", "-format", "%w %h", str(img)],
                         check=True, capture_output=True).stdout.decode()
    w, h = out.split()[:2]
    return int(w), int(h)


def draw(img: Path, dst: Path, *, cx: int, cy: int, mw: int,
         letter: str | None, fill: str, stroke: str, calibrate: bool = False,
         feather: float = 0.0, cover: tuple[str, float] | None = None) -> None:
    if not calibrate and (feather > 0 or cover):
        return _draw_feathered(img, dst, cx=cx, cy=cy, mw=mw, letter=letter,
                               fill=fill, stroke=stroke, feather=feather, cover=cover)
    cmd = ["convert", str(img)]
    if calibrate:
        half = mw // 2
        cmd += ["-fill", "none", "-stroke", "#00FF00", "-strokewidth", "3",
                "-draw", f"rectangle {cx-half},{cy-half} {cx+half},{cy+half}",
                "-draw", f"line {cx-half-14},{cy} {cx+half+14},{cy}",
                "-draw", f"line {cx},{cy-half-14} {cx},{cy+half+14}"]
    else:
        wm, hm, kind = SHAPES[letter]
        hw = max(int(mw * wm / 2), 2)
        hh = max(int(mw * hm / 2), 2)
        cmd += ["-fill", fill, "-stroke", stroke, "-strokewidth", str(max(mw // 24, 2)),
                "-draw", f"ellipse {cx},{cy} {hw},{hh} 0,360"]
        if kind == "teeth":
            cmd += ["-fill", "#FFFFFF", "-stroke", "none",
                    "-draw", f"rectangle {cx-hw+max(hw//8,2)},{cy-hh+2} "
                             f"{cx+hw-max(hw//8,2)},{cy-hh+max(hh//2,3)}"]
        elif kind == "tongue":
            cmd += ["-fill", "#C4566B", "-stroke", "none",
                    "-draw", f"ellipse {cx},{cy+hh//3} {hw//2},{max(hh//3,2)} 0,360"]
    cmd.append(str(dst))
    _run(cmd)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--image", required=True, help="the character picture")
    ap.add_argument("--out", help="directory for A.png … X.png (required unless --calibrate)")
    ap.add_argument("--mouth-x", type=float, default=0.50, help="0-1 across the image")
    ap.add_argument("--mouth-y", type=float, default=0.62, help="0-1 down the image")
    ap.add_argument("--mouth-w", type=float, default=0.12, help="mouth width as a fraction of image width")
    ap.add_argument("--fill", default="#3A1618", help="inside of the mouth")
    ap.add_argument("--stroke", default="#240D0E", help="mouth outline")
    ap.add_argument("--cover", default="auto",
                    help="paint out the artist's existing mouth first: 'auto' samples the "
                         "skin just above the mouth, or give a hex colour, or 'none'")
    ap.add_argument("--cover-scale", type=float, default=1.9,
                    help="how much wider than the mouth the cover patch is")
    ap.add_argument("--feather", type=float, default=0.03,
                    help="blur the mouth edge, as a fraction of mouth width. 0 = hard edge "
                         "(fine for flat cartoons); ~0.06 blends into detailed artwork")
    ap.add_argument("--calibrate", action="store_true",
                    help="write ONE preview with the mouth box marked, then stop")
    args = ap.parse_args()

    if not shutil.which("convert"):
        print("ImageMagick `convert` not found (sudo apt install imagemagick)", file=sys.stderr)
        return 2
    img = Path(args.image)
    if not img.is_file():
        print(f"no such image: {img}", file=sys.stderr)
        return 2

    w, h = dimensions(img)
    cx, cy = int(w * args.mouth_x), int(h * args.mouth_y)
    mw = max(int(w * args.mouth_w), 6)

    cover = None
    if args.cover and args.cover.lower() != "none":
        if args.cover.lower() == "auto":
            colour = sample_skin(img, cx, cy, mw)
        else:
            colour = args.cover
        cover = (colour, args.cover_scale)

    if args.calibrate:
        dst = img.with_name(f"{img.stem}-calibrate.png")
        draw(img, dst, cx=cx, cy=cy, mw=mw, letter=None,
             fill=args.fill, stroke=args.stroke, calibrate=True)
        print(f"wrote {dst}  ({w}x{h}, mouth box {mw}px at {cx},{cy})")
        print("Look at it. Move --mouth-x/--mouth-y, resize with --mouth-w, run again.")
        return 0

    if not args.out:
        print("--out is required unless you pass --calibrate", file=sys.stderr)
        return 2
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    for letter in SHAPES:
        draw(img, out_dir / f"{letter}.png", cx=cx, cy=cy, mw=mw, letter=letter,
             fill=args.fill, stroke=args.stroke, feather=args.feather, cover=cover)
    # Record the geometry next to the character. The HeyGen path needs a head crop and
    # the mouth position is the only reliable anchor we have for finding one.
    cfg = img.parent / "character.json"
    cfg.write_text(json.dumps({
        "image": img.name,
        "width": w, "height": h,
        "mouth_x": args.mouth_x, "mouth_y": args.mouth_y, "mouth_w": args.mouth_w,
        "cover_scale": args.cover_scale, "feather": args.feather,
    }, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {cfg}")

    print(f"wrote {len(SHAPES)} sprites to {out_dir}  (from {img.name}, {w}x{h})"
          + (f"  cover={cover[0]}" if cover else "  cover=none"))
    print(f"test it:  python3 -m clemtock avatar --sprites {out_dir} --text \"howdy\" --out /tmp/test.mp4")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
