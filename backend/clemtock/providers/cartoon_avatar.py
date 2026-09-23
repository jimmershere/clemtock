"""Cartoon avatar — text in, talking-mascot video out. No GPU, no API, no per-clip fee.

Chains the three free pieces:

    text ──► Chatterbox ──► voice.wav ──► Rhubarb ──► mouth timeline ──┐
                                 │                                     │
                                 └──────────── ffmpeg ◄── sprite set ◄──┘
                                                 │
                                              out.mp4

Implements `AvatarProvider`, so it is a drop-in alternative to HeyGen: the pipeline
calls `generate(text, out)` either way and does not care which one answered.

Sprite sets are a directory of A.png … F.png (G/H/X optional) — see
rhubarb_lipsync for what each shape means. portrender's `mascot-sheet` template is
the intended way to draw them.

Compositing note: frames are assembled with ffmpeg's concat demuxer, one entry per
mouth cue with that cue's duration, rather than by writing every frame to disk. A
15-second line is ~60 cue entries instead of 450 PNGs, and ffmpeg does the timing.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from . import rhubarb_lipsync as rhubarb
from .base import AvatarProvider, ProviderUnavailable
from .chatterbox_voice import ChatterboxVoice


def _ffmpeg() -> str:
    exe = shutil.which(os.environ.get("FFMPEG_BIN", "ffmpeg"))
    if not exe:
        raise ProviderUnavailable("ffmpeg not found (sudo apt install ffmpeg)")
    return exe


class CartoonAvatarProvider(AvatarProvider):
    name = "cartoon"

    def __init__(self, sprites_dir: Path, *, voice_ref: Path | None = None,
                 background: Path | None = None, width: int = 1080, height: int = 1920,
                 fps: int = 30, bg_color: str = "black", keep_workdir: bool = False):
        self.sprites_dir = Path(sprites_dir)
        self.voice = ChatterboxVoice(voice_ref=voice_ref)
        self.background = Path(background) if background else None
        self.width, self.height, self.fps = width, height, fps
        self.bg_color = bg_color
        self.keep_workdir = keep_workdir

    # ---------- health ----------
    def available(self) -> bool:
        try:
            rhubarb.binary()
            _ffmpeg()
        except ProviderUnavailable:
            return False
        return self.voice.available() and self.sprites_dir.is_dir()

    # ---------- the chain ----------
    def generate(self, text: str, out: Path, *, avatar_id: str | None = None,
                 voice_id: str | None = None) -> Path:
        """avatar_id selects a sprite set under sprites_dir; voice_id a reference WAV.

        Both are optional: with neither, the provider uses the sprite directory it was
        constructed with and Chatterbox's default voice.
        """
        out = Path(out)
        out.parent.mkdir(parents=True, exist_ok=True)

        sprites_dir = self.sprites_dir / avatar_id if avatar_id else self.sprites_dir
        sprites = rhubarb.load_sprites(sprites_dir)

        work = Path(tempfile.mkdtemp(prefix="cartoon-"))
        try:
            wav = self.voice.synthesize(
                text, work / "voice.wav",
                voice_ref=Path(voice_id) if voice_id else None)
            timeline = rhubarb.analyse(wav, dialog=text)
            concat = self._write_concat(timeline, sprites, work)
            self._render(concat, wav, out)
            return out
        finally:
            if self.keep_workdir:
                print(f"[cartoon] workdir kept: {work}")
            else:
                shutil.rmtree(work, ignore_errors=True)

    # ---------- pieces ----------
    def _write_concat(self, timeline, sprites: dict, work: Path) -> Path:
        """One concat entry per mouth cue. Durations come straight from rhubarb."""
        lines: list[str] = []
        last: Path | None = None
        for cue in timeline.cues:
            if cue.duration <= 0:
                continue
            sprite = timeline.sprite_for(cue.value, sprites).resolve()
            lines.append(f"file '{sprite}'")
            lines.append(f"duration {cue.duration:.4f}")
            last = sprite
        if last is None:
            raise ProviderUnavailable("mouth timeline had no positive-duration cues")
        # concat demuxer quirk: the final entry needs repeating without a duration,
        # otherwise ffmpeg drops the last cue entirely.
        lines.append(f"file '{last}'")
        path = work / "cues.txt"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path

    def _render(self, concat: Path, wav: Path, out: Path) -> None:
        w, h = self.width, self.height
        # Fit the sprite inside the frame without distorting it, then pad to size.
        fit = (f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
               f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color={self.bg_color},"
               f"fps={self.fps},format=yuv420p")

        cmd = [_ffmpeg(), "-y", "-hide_banner", "-loglevel", "error"]
        if self.background:
            if not self.background.is_file():
                raise ProviderUnavailable(f"background not found: {self.background}")
            cmd += ["-loop", "1", "-i", str(self.background)]
        cmd += ["-f", "concat", "-safe", "0", "-i", str(concat), "-i", str(wav)]

        if self.background:
            # Sprites keep their alpha here, so the mascot sits on the backdrop.
            filt = (f"[0:v]scale={w}:{h}:force_original_aspect_ratio=increase,"
                    f"crop={w}:{h}[bg];"
                    f"[1:v]scale={w}:{h}:force_original_aspect_ratio=decrease[mouth];"
                    f"[bg][mouth]overlay=(W-w)/2:(H-h)/2:shortest=1,"
                    f"fps={self.fps},format=yuv420p[v]")
            cmd += ["-filter_complex", filt, "-map", "[v]", "-map", "2:a"]
        else:
            cmd += ["-vf", fit, "-map", "0:v", "-map", "1:a"]

        cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", "20",
                "-c:a", "aac", "-b:a", "128k", "-shortest", str(out)]

        proc = subprocess.run(cmd, capture_output=True, timeout=1800)
        if proc.returncode != 0 or not out.is_file():
            raise ProviderUnavailable(
                f"ffmpeg failed ({proc.returncode}): "
                f"{proc.stderr.decode('utf-8','replace')[-500:]}")
