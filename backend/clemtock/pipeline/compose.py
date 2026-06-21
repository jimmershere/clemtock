"""Phase 6 — composite real video/avatar clips + audio under the graphics layer.

Model: one ink base + real clips placed at their scene windows + a single transparent
graphics overlay on top.

  1. render the graphics layer with alpha (render-headless --alpha) -> overlay.mov (qtrle).
     In alpha mode, video/avatar scenes are "holes"; every other scene is opaque.
  2. ffmpeg: ink base (#0B1018, full duration); for each clip scene, scale-to-cover the clip
     and overlay it only during [start,end]; then overlay the alpha graphics on top.
  3. audio: each clip's audio is delayed to its scene start and amixed.

If the ad-script has no real clips, falls back to the plain DOM render (render-headless).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

_INK = "0x0B1018"


def _tool(name: str) -> str:
    home = os.environ.get("HOME", "")
    local = Path(home) / "bin" / name
    return str(local) if local.exists() else (shutil.which(name) or name)


def _has_audio(path: Path) -> bool:
    try:
        out = subprocess.run(
            [_tool("ffprobe"), "-v", "error", "-select_streams", "a",
             "-show_entries", "stream=index", "-of", "csv=p=0", str(path)],
            capture_output=True, text=True, timeout=30)
        return bool(out.stdout.strip())
    except Exception:
        return False


def _resolve(src: str, repo: Path) -> Path:
    p = Path(src)
    return p if p.is_absolute() else (repo / "web" / src)


def _render_overlay(script: Path, repo: Path, fps: int) -> Path:
    overlay = repo / "out" / "overlay.mov"
    subprocess.run(
        ["node", str(repo / "web" / "render-headless.mjs"), "--alpha",
         "--script", str(script), "--out", str(overlay), "--fps", str(fps)],
        check=True)
    return overlay


def _plain_export(script: Path, repo: Path, out: Path, fps: int) -> Path:
    subprocess.run(
        ["node", str(repo / "web" / "render-headless.mjs"),
         "--script", str(script), "--out", str(out), "--fps", str(fps)],
        check=True)
    return out


def run(script_path: Path, repo: Path, out_path: Path, fps: int = 30) -> dict:
    doc = json.loads(script_path.read_text())
    dur = float(doc.get("duration", 15))
    assets = doc.get("assets") or {}

    clip_scenes = []  # (scene, clip_path, has_audio)
    for sc in doc.get("scenes", []):
        aid = (sc.get("assets") or [None])[0]
        a = assets.get(aid) if aid else None
        if a and a.get("kind") in ("video", "avatar") and a.get("src"):
            src = _resolve(a["src"], repo)
            if src.exists():
                clip_scenes.append((sc, src, _has_audio(src)))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    if not clip_scenes:
        _plain_export(script_path, repo, out_path, fps)
        return {"mode": "plain", "clips": 0, "out": str(out_path)}

    overlay = _render_overlay(script_path, repo, fps)

    inputs: list[str] = []
    for _, src, _a in clip_scenes:
        inputs += ["-i", str(src)]
    inputs += ["-i", str(overlay)]
    ov_idx = len(clip_scenes)

    fc = [f"color=c={_INK}:s=1080x1920:r={fps}:d={dur}[base]"]
    cur = "base"
    audio = []
    for i, (sc, _src, has_a) in enumerate(clip_scenes):
        s, e = float(sc["start"]), float(sc["end"])
        d = round(e - s, 3)
        if sc.get("fit") == "contain":
            # letterbox onto the ink bg — keeps terminal/screen-capture text uncropped
            scale = (f"scale=1080:1920:force_original_aspect_ratio=decrease,"
                     f"pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color={_INK}")
        else:
            scale = ("scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920")
        fc.append(f"[{i}:v]{scale},trim=0:{d},setpts=PTS-STARTPTS+{s}/TB[c{i}]")
        nxt = f"b{i}"
        fc.append(f"[{cur}][c{i}]overlay=enable='between(t,{s},{e})':x=0:y=0[{nxt}]")
        cur = nxt
        if has_a:
            ms = int(s * 1000)
            fc.append(f"[{i}:a]adelay={ms}|{ms}[a{i}]")
            audio.append(f"[a{i}]")

    fc.append(f"[{cur}][{ov_idx}:v]overlay=0:0:format=auto,"
              f"trim=0:{dur},setpts=PTS-STARTPTS,format=yuv420p[vout]")

    maps = ["-map", "[vout]"]
    if audio:
        if len(audio) > 1:
            fc.append(f"{''.join(audio)}amix=inputs={len(audio)}:dropout_transition=0[aout]")
        else:
            fc.append(f"{audio[0]}anull[aout]")
        maps += ["-map", "[aout]", "-c:a", "aac", "-b:a", "192k"]

    cmd = [_tool("ffmpeg"), "-y"] + inputs + ["-filter_complex", ";".join(fc)] + maps + [
        "-t", str(dur), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18",
        "-movflags", "+faststart", str(out_path)]
    subprocess.run(cmd, check=True)
    return {"mode": "composite", "clips": len(clip_scenes),
            "audio_tracks": len(audio), "out": str(out_path)}
