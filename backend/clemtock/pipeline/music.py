"""Optional royalty-free music bed for a rendered ad (Phase 7 publish helper).

A music bed is OPTIONAL — narrated/tutorial spots can skip it. When applied, the
chosen track is looped/trimmed to the exact video length and muxed in. By default the
bed becomes the soundtrack (these snip ads have no audio); pass duck=True to keep any
existing audio (e.g. a voice-over) and tuck the music under it.

NOTE: do NOT score TikTok uploads — TikTok requires sound to be added in-app for
licensing/discovery, so the TikTok publish path always posts the raw video.

Tracks live under assets/music/<genre>/*.{mp3,m4a,wav,aac,ogg}. Stdlib-only.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

_AUDIO_EXT = {".mp3", ".m4a", ".wav", ".aac", ".ogg", ".flac"}


class MusicError(Exception):
    pass


def _tool(name: str) -> str:
    home = os.environ.get("HOME", "")
    local = Path(home) / "bin" / name
    return str(local) if local.exists() else (shutil.which(name) or name)


def _music_dir(repo: Path) -> Path:
    return repo / "assets" / "music"


def list_tracks(repo: Path) -> list[dict]:
    """Scan assets/music/<genre>/* and return [{id, name, genre, src}] sorted by genre."""
    root = _music_dir(repo)
    out: list[dict] = []
    if not root.exists():
        return out
    for p in sorted(root.rglob("*")):
        if p.is_file() and p.suffix.lower() in _AUDIO_EXT:
            genre = p.parent.name if p.parent != root else "misc"
            out.append({"id": p.stem, "name": p.stem.replace("_", " ").replace("-", " ").title(),
                        "genre": genre, "src": str(p.relative_to(repo))})
    out.sort(key=lambda t: (t["genre"], t["id"]))
    return out


def resolve_track(repo: Path, name: str) -> Path:
    """Find a track by id/stem or by a path under assets/music."""
    cand = Path(name)
    if cand.is_file():
        return cand
    for t in list_tracks(repo):
        if t["id"] == name or t["src"].endswith(name):
            return repo / t["src"]
    have = ", ".join(t["id"] for t in list_tracks(repo)) or "(none)"
    raise MusicError(f"music track {name!r} not found; have: {have}")


def _has_audio(path: Path) -> bool:
    try:
        out = subprocess.run(
            [_tool("ffprobe"), "-v", "error", "-select_streams", "a",
             "-show_entries", "stream=index", "-of", "csv=p=0", str(path)],
            capture_output=True, text=True, timeout=30)
        return bool(out.stdout.strip())
    except Exception:
        return False


def score(video: Path, track: Path, out: Path, *, gain_db: float = -3.0,
          duck: bool = False) -> dict:
    """Mux `track` (looped/trimmed to video length) into `video` -> `out`.

    Default: the bed becomes the soundtrack. duck=True: keep existing audio and tuck the
    music under it (only meaningful when the video already has an audio track).
    """
    if not video.exists():
        raise MusicError(f"video not found: {video}")
    if not track.exists():
        raise MusicError(f"track not found: {track}")
    out.parent.mkdir(parents=True, exist_ok=True)

    vol = f"volume={gain_db}dB"
    if duck and _has_audio(video):
        # keep the original audio (e.g. narration), tuck a quieter music bed under it
        fc = (f"[1:a]{vol},volume=0.30,aloop=loop=-1:size=2e9[m];"
              f"[0:a][m]amix=inputs=2:duration=first:dropout_transition=0[a]")
        cmd = [_tool("ffmpeg"), "-y", "-i", str(video), "-i", str(track),
               "-filter_complex", fc, "-map", "0:v", "-map", "[a]",
               "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", str(out)]
    else:
        # bed-only: loop the track and cut to the video length; copy video stream as-is
        cmd = [_tool("ffmpeg"), "-y", "-i", str(video), "-stream_loop", "-1", "-i", str(track),
               "-filter:a", vol, "-map", "0:v", "-map", "1:a",
               "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", str(out)]
    subprocess.run(cmd, check=True)
    return {"out": str(out), "track": track.stem, "duck": bool(duck and _has_audio(video))}
