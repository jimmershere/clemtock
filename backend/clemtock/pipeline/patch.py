"""Surgical single-scene edits to an ad-script, so a tweak never re-authors the run.

`ad-script.json` is the durable source of truth for an ad: the OpenRouter script step
and the AI asset generation both feed it, and `compose` rebuilds the video from it.
This module lets an operator change ONE scene (its template, media, copy, fit, motion,
or timing) in place — leaving every other scene, the palette, and untouched assets
exactly as they were. The previous ad-script is always backed up first, so no work is
lost. Stdlib-only.
"""
from __future__ import annotations

import json
import re
import shutil
import time
from pathlib import Path

_VIDEO_EXT = {".mp4", ".mov", ".webm", ".m4v"}
_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
_COPY_KEYS = {"kicker", "headline", "sub", "cta"}


class PatchError(Exception):
    pass


def _slug(stem: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "_", stem).strip("_").lower()
    return s or "asset"


def _kind_for(path: Path, override: str | None) -> str:
    if override:
        return override
    ext = path.suffix.lower()
    if ext in _VIDEO_EXT:
        return "video"
    if ext in _IMAGE_EXT:
        return "image"
    raise PatchError(f"cannot infer asset kind for {path.name}; pass asset_kind=")


def _ingest_asset(src_file: Path, repo: Path, kind: str) -> tuple[str, dict]:
    """Copy a local media file into web/assets/clips and return (asset_id, asset_entry)."""
    sub = "clips" if kind == "video" else "stills"
    dest_dir = repo / "web" / "assets" / sub
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src_file.name
    if src_file.resolve() != dest.resolve():
        shutil.copy2(src_file, dest)
    rel = dest.relative_to(repo / "web")
    aid = _slug(src_file.stem)
    return aid, {"kind": kind, "source": "upload", "src": str(rel)}


def apply(script_path: Path, scene_id: str, repo: Path, *,
          template: str | None = None,
          set_asset: str | None = None,
          asset_kind: str | None = None,
          copy: dict | None = None,
          fit: str | None = None,
          motion: str | None = None,
          start: float | None = None,
          end: float | None = None) -> dict:
    """Edit a single scene in script_path. Returns a summary of what changed.

    set_asset may be a path to a local media file (copied in + registered as a new
    top-level asset) OR the id of an asset already present in the script.
    """
    if not script_path.exists():
        raise PatchError(f"ad-script not found: {script_path}")
    doc = json.loads(script_path.read_text())
    scenes = doc.get("scenes") or []
    scene = next((s for s in scenes if str(s.get("id")) == str(scene_id)), None)
    if scene is None:
        ids = ", ".join(str(s.get("id")) for s in scenes)
        raise PatchError(f"no scene with id {scene_id!r}; have: {ids}")

    changed: list[str] = []

    if set_asset is not None:
        assets = doc.setdefault("assets", {})
        cand = Path(set_asset)
        if cand.exists() and cand.is_file():
            kind = _kind_for(cand, asset_kind)
            aid, entry = _ingest_asset(cand, repo, kind)
            assets[aid] = entry
            scene["assets"] = [aid]
            changed.append(f"asset -> {aid} ({kind}, {entry['src']})")
            if template is None and kind == "video" and scene.get("template") != "video":
                template = "video"
        elif set_asset in assets:
            scene["assets"] = [set_asset]
            changed.append(f"asset -> {set_asset} (existing)")
        else:
            raise PatchError(
                f"set_asset {set_asset!r} is neither an existing file nor a known asset id")

    if template is not None:
        scene["template"] = template
        changed.append(f"template -> {template}")

    if copy:
        bad = set(copy) - _COPY_KEYS
        if bad:
            raise PatchError(f"unknown copy key(s): {sorted(bad)}; allowed: {sorted(_COPY_KEYS)}")
        c = scene.get("copy")
        if not isinstance(c, dict):
            c = {} if c is None else {"headline": str(c)}
        for k, v in copy.items():
            if v == "":
                c.pop(k, None)
                changed.append(f"copy.{k} cleared")
            else:
                c[k] = v
                changed.append(f"copy.{k} -> {v!r}")
        scene["copy"] = c

    if fit is not None:
        if fit not in ("cover", "contain"):
            raise PatchError("fit must be 'cover' or 'contain'")
        scene["fit"] = fit
        changed.append(f"fit -> {fit}")

    if motion is not None:
        scene["motion"] = {"type": motion}
        changed.append(f"motion -> {motion}")

    if start is not None:
        scene["start"] = start
        changed.append(f"start -> {start}")
    if end is not None:
        scene["end"] = end
        changed.append(f"end -> {end}")

    if not changed:
        raise PatchError("nothing to patch; pass at least one of "
                         "template/set_asset/copy/fit/motion/start/end")

    # back up the previous ad-script so a tweak can never lose prior work
    backups = script_path.parent / ".backups"
    backups.mkdir(exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%S")
    backup = backups / f"{script_path.stem}.{stamp}.json"
    shutil.copy2(script_path, backup)

    script_path.write_text(json.dumps(doc, indent=2) + "\n")
    return {"scene": scene_id, "changed": changed, "backup": str(backup),
            "script": str(script_path)}
