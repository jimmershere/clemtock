"""Rhubarb Lip Sync — audio -> a timeline of 2D mouth shapes. CPU, instant, MIT.

This is the piece that makes cartoon avatars cost nothing. A photoreal talking head
needs a diffusion model to hallucinate a face in motion; a drawn mascot does not — its
mouth is a finite set of pictures, and lip-sync is choosing which picture is on screen
at each moment. Rhubarb solves exactly that, offline, in about real time.

Shapes are the Preston Blair set that every 2D animator already knows:

    A  closed          M, B, P
    B  slight open     most consonants; also the "idle talking" shape
    C  open            E, some vowels
    D  wide open       AI, "aa"
    E  rounded small   O
    F  puckered        U, W
    G  teeth on lip    F, V            (extended set)
    H  tongue up       L               (extended set)
    X  rest            silence         (extended set)

A sprite set therefore needs at most nine images. Six (A-F) is a complete, usable
mouth; G/H/X are polish. `MouthTimeline.sprite_for` degrades to the nearest shape it
has rather than failing, so a six-image set works on day one.

Binary lives in vendor/rhubarb/ (87 MB, gitignored — see scripts/setup-avatar-chain.sh).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .base import ProviderUnavailable

# providers/ is one level deeper than config.py, so this is parents[3], not [2]:
# backend/clemtock/providers/x.py -> providers, clemtock, backend, <repo>.
_REPO = Path(__file__).resolve().parents[3]
DEFAULT_BIN = _REPO / "vendor" / "rhubarb" / "rhubarb"

# Where to fall back when a sprite set lacks a shape, in order of visual closeness.
# Every chain ends at "A" because a closed mouth is the safest thing to show.
_FALLBACK: dict[str, tuple[str, ...]] = {
    "A": (),
    "B": ("A",),
    "C": ("B", "A"),
    "D": ("C", "B", "A"),
    "E": ("C", "B", "A"),
    "F": ("E", "C", "B", "A"),
    "G": ("B", "A"),
    "H": ("C", "B", "A"),
    "X": ("A",),
}


@dataclass(frozen=True)
class MouthCue:
    start: float
    end: float
    value: str      # one of A-H, X

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


@dataclass
class MouthTimeline:
    cues: list[MouthCue]
    duration: float

    def sprite_for(self, shape: str, sprites: dict[str, Path]) -> Path:
        """Best available image for `shape`, degrading through _FALLBACK."""
        for candidate in (shape, *_FALLBACK.get(shape, ())):
            if candidate in sprites:
                return sprites[candidate]
        if sprites:                       # nothing matched: any mouth beats crashing
            return next(iter(sprites.values()))
        raise ProviderUnavailable("sprite set is empty")

    def shapes_used(self) -> set[str]:
        return {c.value for c in self.cues}


def binary() -> Path:
    """Locate the rhubarb executable, honouring RHUBARB_BIN."""
    env = os.environ.get("RHUBARB_BIN", "").strip()
    if env:
        p = Path(env)
        if p.is_file():
            return p
        raise ProviderUnavailable(f"RHUBARB_BIN={env} is not a file")
    if DEFAULT_BIN.is_file():
        return DEFAULT_BIN
    found = shutil.which("rhubarb")
    if found:
        return Path(found)
    raise ProviderUnavailable(
        f"rhubarb not found at {DEFAULT_BIN} — run scripts/setup-avatar-chain.sh")


def available() -> bool:
    try:
        binary()
        return True
    except ProviderUnavailable:
        return False


def analyse(wav: Path, *, dialog: str | None = None, extended: bool = True,
            timeout: int = 900) -> MouthTimeline:
    """Run rhubarb over a WAV and return the mouth timeline.

    `dialog` is the spoken text. Passing it is not cosmetic: rhubarb uses it to
    constrain recognition, which measurably improves shape accuracy — and we always
    have it, because we just synthesised the audio from it.
    """
    wav = Path(wav)
    if not wav.is_file():
        raise ProviderUnavailable(f"no such audio file: {wav}")

    # No -o: rhubarb writes the export to stdout. -q silences the progress chatter on
    # stderr (--machineReadable only reformats that chatter, it does not move the export).
    cmd = [str(binary()), "-f", "json", "-q"]
    if extended:
        # A-H + X rather than A-F. Costs nothing; sprite_for degrades if art is missing.
        cmd += ["--extendedShapes", "GHX"]
    tmp_dialog = None
    if dialog:
        tmp_dialog = Path(tempfile.mkstemp(suffix=".txt")[1])
        tmp_dialog.write_text(dialog, encoding="utf-8")
        cmd += ["--dialogFile", str(tmp_dialog)]
    cmd.append(str(wav))

    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired as e:
        raise ProviderUnavailable(f"rhubarb timed out after {timeout}s") from e
    finally:
        if tmp_dialog:
            tmp_dialog.unlink(missing_ok=True)

    if proc.returncode != 0:
        raise ProviderUnavailable(
            f"rhubarb exited {proc.returncode}: {proc.stderr.decode('utf-8','replace')[:400]}")

    try:
        data = json.loads(proc.stdout.decode("utf-8", "replace"))
    except json.JSONDecodeError as e:
        raise ProviderUnavailable(
            f"rhubarb returned non-JSON: {proc.stdout[:200]!r}") from e

    cues = [MouthCue(float(c["start"]), float(c["end"]), str(c["value"]).upper())
            for c in data.get("mouthCues", [])]
    if not cues:
        raise ProviderUnavailable("rhubarb produced no mouth cues")
    return MouthTimeline(cues=cues, duration=cues[-1].end)


def load_sprites(sprites_dir: Path) -> dict[str, Path]:
    """Map shape letter -> image, from files named A.png … X.png (any case/extension)."""
    sprites_dir = Path(sprites_dir)
    if not sprites_dir.is_dir():
        raise ProviderUnavailable(f"sprite directory not found: {sprites_dir}")
    out: dict[str, Path] = {}
    for f in sorted(sprites_dir.iterdir()):
        if f.is_file() and f.suffix.lower() in (".png", ".webp", ".jpg", ".jpeg"):
            key = f.stem.strip().upper()
            if key in _FALLBACK:
                out.setdefault(key, f)
    if not out:
        raise ProviderUnavailable(
            f"no mouth sprites in {sprites_dir} — expected A.png … F.png (G/H/X optional)")
    return out
