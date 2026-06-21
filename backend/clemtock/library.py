"""Asset library: organize assets/ into a category tree and (re)write library.json.

`rebuild()` is importable so the server can rescan on a timer, on upload, and before every
plan/execute. Known files get curated roles/names from MAP; anything else (drop-ins, uploads)
is auto-discovered with category = its parent dir and role ["reference"], so new assets are
never missed.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ASSETS = REPO / "assets"
THUMBS = ASSETS / ".thumbs"
_IMG = {".png", ".jpg", ".jpeg", ".webp"}
# default roles for drop-ins, inferred from their folder
_DIR_ROLE = {"characters": ["character"], "mascots": ["hero", "character"],
             "logos": ["logo"], "creatures": ["character"], "uploads": ["reference"]}

# curated: filename -> (category, roles, name, tags)
MAP = {
    "local81-portw.png": ("logos", ["logo"], "Local 81 Emblem", ["local81", "brand", "badge"]),
    "portwr-out.png":    ("logos", ["logo"], "Portwright Wordmark", ["portwright", "brand"]),
    "mh-bw-logo.png":    ("logos", ["logo"], "Madd Hatchery Logo", ["madd-hatchery", "brand"]),
    "l81-clem.png":      ("mascots", ["hero", "character"], "Clem — Local 81", ["clem", "local81", "robot"]),
    "portwr-clem.png":   ("mascots", ["hero", "character"], "Clem — Portwright Beach", ["clem", "portwright"]),
    "fun-faith.png":     ("characters", ["character"], "Faith", ["persona", "woman"]),
    "hot-tpk.png":       ("characters", ["character"], "Trish — TPK", ["persona", "tpk"]),
    "mikey.png":         ("characters", ["character"], "Mikey", ["persona", "man"]),
    "paigela.png":       ("characters", ["character"], "Paigela", ["persona", "woman"]),
    "teen-trish.png":    ("characters", ["character"], "Teen Trish", ["persona", "teen"]),
    "tpk-baby-chick.png": ("characters", ["character"], "TPK — Baby Chick", ["persona", "tpk"]),
    "tpk-basket-billy.png": ("characters", ["character"], "TPK — Basket Billy", ["persona", "tpk"]),
    "seamus.png":        ("creatures", ["character"], "Seamus", ["pet", "dog"]),
    "uggy.png":          ("creatures", ["character"], "Uggy", ["creature", "cartoon"]),
}

MODELS = [
    {"id": "cartoon", "provider": "heygen", "avatar_ref": "HEYGEN_CARTOON_AVATAR_ID",
     "voice_ref": "HEYGEN_VOICE_CLONE_ID", "name": "Cartoon Spokesperson", "roles": ["model"]},
    {"id": "jake", "provider": "heygen", "avatar_ref": "HEYGEN_JAKE_AVATAR_ID",
     "voice_ref": "HEYGEN_VOICE_CLONE_ID", "name": "Jake", "roles": ["model"]},
]


def _dims(p: Path):
    try:
        o = subprocess.run(["identify", "-format", "%w %h", str(p)],
                           capture_output=True, text=True, timeout=20).stdout.split()
        return int(o[0]), int(o[1])
    except Exception:
        return None, None


def _thumb(src: Path, dst: Path):
    if dst.exists() and dst.stat().st_mtime >= src.stat().st_mtime:
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["convert", str(src), "-thumbnail", "320x320", "-background", "none", str(dst)],
                   check=False)


def _pretty(stem: str) -> str:
    return stem.replace("-", " ").replace("_", " ").title()


def rebuild() -> dict:
    THUMBS.mkdir(parents=True, exist_ok=True)
    assets, seen = [], set()
    for p in sorted(ASSETS.rglob("*")):
        if p.suffix.lower() not in _IMG or ".thumbs" in p.parts or p.name in seen:
            continue
        seen.add(p.name)
        if p.name in MAP:
            cat, roles, name, tags = MAP[p.name]
            dest = ASSETS / cat / p.name
            dest.parent.mkdir(exist_ok=True)
            if p.resolve() != dest.resolve():
                shutil.move(str(p), str(dest))
        else:
            # auto-discovered: category = parent dir (root/uploads -> "uploads"); role from dir
            parent = p.parent.name
            cat = "uploads" if p.parent == ASSETS or parent in ("", "assets") else parent
            roles = _DIR_ROLE.get(cat, ["reference"])
            name, tags, dest = _pretty(p.stem), ["dropin"], p
        _thumb(dest, THUMBS / dest.name)
        w, h = _dims(dest)
        assets.append({"id": dest.stem, "file": str(dest.relative_to(ASSETS)),
                       "thumb": f".thumbs/{dest.name}", "category": cat, "roles": roles,
                       "name": name, "tags": tags, "w": w, "h": h})

    lib = {
        "version": 1,
        "roles": {"hero": "brand mascot / focal image", "character": "illustrated persona",
                  "model": "talking avatar (HeyGen)", "logo": "brand mark",
                  "reference": "uploaded reference / drop-in"},
        "categories": sorted({a["category"] for a in assets}),
        "assets": sorted(assets, key=lambda a: (a["category"], a["name"])),
        "models": MODELS,
    }
    (ASSETS / "library.json").write_text(json.dumps(lib, indent=2))
    return {"assets": len(assets), "categories": lib["categories"]}


if __name__ == "__main__":
    print(rebuild())
