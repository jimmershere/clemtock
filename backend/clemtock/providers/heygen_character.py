"""Drive HeyGen with YOUR character instead of a stock presenter.

HeyGen's 1,264 stock avatars are all photoreal people — there is not one cartoon among
them (checked 2026-09-23). The only way to animate a brand's own mascot is the
*talking photo* path: upload a picture, get an id, drive that id with speech.

This module owns the two fiddly parts:

1. **The crop.** HeyGen runs a face model. Handed a full-body figure where the head is a
   sixth of the frame, it has almost nothing to work with. We cut a square head-and-
   shoulders portrait, anchored on the mouth position already recorded in
   `character.json` by `sprites-from-character.py`, and flatten the transparency —
   a PNG alpha channel is not a background.

2. **The cache.** Every upload creates a new photo avatar server-side, so re-uploading
   the same character on every render litters the account. The id is cached in
   `brands/<slug>/heygen.json` and reused until the source image changes.

Quality note, measured: this produces genuinely professional lip-sync — real lip shapes,
visible teeth, jaw and beard moving with the speech — at **~$0.019 per second of video**
($0.10 for 5.3 s, observed on the wallet). The local Chatterbox+Rhubarb chain is free but
visibly cruder. For paying client work HeyGen is cheap enough to be the default.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

from .base import ProviderUnavailable

PORTRENDER_BRANDS = Path(os.environ.get("PORTRENDER_BRANDS_DIR", "/app/portrender/brands"))

# Portrait geometry, expressed in mouth-widths because that is the one measurement we
# already have. Tuned against the jimmer character; override per brand in character.json.
PORTRAIT_SIDE_MW = 10.0     # square side
PORTRAIT_DROP_MW = 0.8      # shift the centre below the mouth, to include some shoulder


def brand_dir(slug: str) -> Path:
    d = PORTRENDER_BRANDS / slug
    if not d.is_dir():
        raise ProviderUnavailable(f"no brand directory: {d}")
    return d


def character_image(slug: str) -> Path:
    d = brand_dir(slug)
    for name in ("character.png", "character.jpg", "character.jpeg"):
        p = d / name
        if p.is_file():
            return p
    raise ProviderUnavailable(
        f"no character image for {slug!r}: expected {d}/character.png")


def _geometry(slug: str) -> dict:
    cfg = brand_dir(slug) / "character.json"
    if cfg.is_file():
        try:
            return json.loads(cfg.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    # Centre-ish fallback. Better to render something than to refuse, but the crop will
    # only be right by luck — run sprites-from-character.py to record real coordinates.
    return {"mouth_x": 0.5, "mouth_y": 0.5, "mouth_w": 0.08}


def make_portrait(slug: str, dst: Path, *, side_px: int = 768,
                  bg: str = "#1b1b1f") -> Path:
    """Square, flattened head-and-shoulders crop — what the face model wants."""
    if not shutil.which("convert"):
        raise ProviderUnavailable("ImageMagick `convert` not found")
    img = character_image(slug)
    g = _geometry(slug)
    out = subprocess.run(["identify", "-format", "%w %h", str(img)],
                         check=True, capture_output=True).stdout.decode().split()
    w, h = int(out[0]), int(out[1])

    mw_px = max(float(g.get("mouth_w", 0.08)) * w, 8.0)
    side = int(min(max(mw_px * PORTRAIT_SIDE_MW, 64), min(w, h)))
    cx = float(g.get("mouth_x", 0.5)) * w
    cy = float(g.get("mouth_y", 0.5)) * h + mw_px * PORTRAIT_DROP_MW
    x = int(max(min(cx - side / 2, w - side), 0))
    y = int(max(min(cy - side / 2, h - side), 0))

    dst.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["convert", str(img), "-crop", f"{side}x{side}+{x}+{y}", "+repage",
                    "-background", bg, "-flatten", "-alpha", "off",
                    "-resize", f"{side_px}x{side_px}", str(dst)],
                   check=True, capture_output=True)
    return dst


def _fingerprint(img: Path) -> str:
    return hashlib.sha256(img.read_bytes()).hexdigest()[:16]


def talking_photo_id(provider, slug: str, *, refresh: bool = False) -> str:
    """Cached talking_photo_id for a brand's character, uploading once if needed."""
    cache_path = brand_dir(slug) / "heygen.json"
    img = character_image(slug)
    fp = _fingerprint(img)

    if cache_path.is_file() and not refresh:
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            if cached.get("fingerprint") == fp and cached.get("talking_photo_id"):
                return cached["talking_photo_id"]
        except json.JSONDecodeError:
            pass

    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        portrait = make_portrait(slug, Path(tmp) / "portrait.png")
        tp = provider.upload_talking_photo(portrait)
    cache_path.write_text(json.dumps(
        {"talking_photo_id": tp, "fingerprint": fp, "source": img.name}, indent=2) + "\n",
        encoding="utf-8")
    return tp
