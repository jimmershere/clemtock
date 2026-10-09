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

2. **The cache.** Every upload creates a new photo avatar *group*. Caching the id in
   `brands/<slug>/heygen.json` stops us re-uploading on every render.

   **Photo avatars are unlimited on this account** — verified 2026-10-09 three ways:
   HeyGen's help article ("Free users can create up to 3 unique photo avatars, while
   Creator, Team and Enterprise users have Unlimited photo avatar slots"), the pricing
   page (Free "Up to 3", Creator $29/mo "Unlimited"), and empirically — twelve groups
   created back to back here with no refusal, then cleaned up.

   So slots are no longer a constraint, and the delete-before-upload dance below is
   retired. Note what is NOT unlimited: **Custom Video Avatars** (digital twins built
   from video) stay capped — 1 on Free/Creator, 5+ on Business, 10+ on Enterprise. This
   pipeline uses photo avatars, so that cap does not bite us.

   History, kept because it explains the shape of this code: on the free tier the quota
   counted **groups**, not photos, and the two are separate resources — deleting the
   talking photo left the group behind, still counting. Three edits to one character
   filled the account and blocked a second character entirely (2026-09-24). That is why
   cleanup targets the *group*. It is now housekeeping rather than a precondition.

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


def brand_voice_id(slug: str) -> str:
    """The voice a brand speaks with, from `brands/<slug>/voice.json`.

    This file existed as documentation for weeks while the pipeline ignored it: the voice
    came from --voice-id or a global env var, so every ad script hard-coded an id. That is
    how `michael` kept a placeholder STOCK voice across three finished ads without anyone
    noticing — the brand file said "PLACEHOLDER, replace before client work" and nothing
    read it. Resolving it here makes the brand directory the single source of truth, so
    changing a character's voice is one file edit rather than a hunt through build scripts.

    Returns "" when unset, so callers can fall back without special-casing.
    """
    f = PORTRENDER_BRANDS / slug / "voice.json"
    if not f.is_file():
        return ""
    try:
        return (json.loads(f.read_text(encoding="utf-8")).get("voice_id") or "").strip()
    except (json.JSONDecodeError, OSError):
        return ""


def _fingerprint(img: Path) -> str:
    return hashlib.sha256(img.read_bytes()).hexdigest()[:16]


def delete_group(provider, group_id: str) -> bool:
    """Release a photo-avatar group. Quota is on groups, and it is only 3."""
    import urllib.error
    import urllib.request
    req = urllib.request.Request(
        f"https://api.heygen.com/v2/avatar_group/{group_id}", method="DELETE",
        headers={"X-Api-Key": provider.api_key, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60):
            return True
    except (urllib.error.HTTPError, urllib.error.URLError):
        return False


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

    # The art changed (or a refresh was forced). Read the previous id, but do NOT release
    # it yet: upload FIRST, delete AFTER.
    #
    # The old order — delete, then upload — existed only to free a slot on the 3-avatar
    # free tier, where the upload would otherwise fail against a quota we were ourselves
    # occupying. Creator makes photo avatars unlimited (verified three ways 2026-10-09:
    # HeyGen's own help article and pricing page both say so, and 12 groups were created
    # back-to-back here without a refusal), so that reason is gone — and the old order is
    # actively unsafe. A failed or interrupted upload left the brand with no avatar at
    # all, having already destroyed the working one.
    stale = ""
    if cache_path.is_file():
        try:
            stale = json.loads(cache_path.read_text(encoding="utf-8")).get("talking_photo_id", "")
        except json.JSONDecodeError:
            stale = ""

    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        portrait = make_portrait(slug, Path(tmp) / "portrait.png")
        tp = provider.upload_talking_photo(portrait)

    # Only now that a replacement exists is the old one safe to drop. Tidiness, not
    # quota — and deletes are free (measured 2026-10-09), unlike uploads at ~79 credits
    # / ~$1.32 each. A failure here costs nothing but a stray group.
    if stale and stale != tp:
        freed = delete_group(provider, stale)
        print(f"heygen: released previous avatar group {stale[:12]}… "
              f"({'ok' if freed else 'failed — harmless, clear it by hand if you care'})")
    cache_path.write_text(json.dumps(
        {"talking_photo_id": tp, "fingerprint": fp, "source": img.name}, indent=2) + "\n",
        encoding="utf-8")
    return tp
