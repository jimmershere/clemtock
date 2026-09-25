"""Chatterbox TTS — text -> speech, optionally in a cloned voice. Local, free, MIT.

Why Chatterbox and not the obvious alternatives: it is **MIT licensed**, which the
popular options are not. XTTS v2 is CPML (non-commercial without contacting Coqui) and
F5-TTS is CC-BY-NC 4.0. Both are recommended everywhere and both are wrong for a shop
that sells things. Kokoro is Apache-2.0 but cannot clone a voice at all.

Runs on CPU. Chatterbox-Nano is reported at ~3x realtime on 8 cores; pop-os has 16
threads. See /app/portrender/docs/local-ai-options.md.

**Consent.** Cloning needs ~5 seconds of reference audio. jimmer confirmed on
2026-09-23 that every voice to be cloned has given express permission. Keep that on
record next to the reference clip — `assets/voices/<name>/CONSENT.md` — because the
reference file alone does not carry the permission with it.

Executed out-of-process in the venv (see _chatterbox_worker.py) so clemtock's runtime
stays stdlib-only.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from ..speech import speakable
from .base import ProviderUnavailable

# providers/ is one level deeper than config.py, so this is parents[3], not [2]:
# backend/clemtock/providers/x.py -> providers, clemtock, backend, <repo>.
_REPO = Path(__file__).resolve().parents[3]
_WORKER = Path(__file__).resolve().parent / "_chatterbox_worker.py"
DEFAULT_VENV_PY = _REPO / ".venv" / "bin" / "python"


def venv_python() -> Path:
    """Interpreter that has chatterbox installed. CLEMTOCK_VENV_PY overrides."""
    env = os.environ.get("CLEMTOCK_VENV_PY", "").strip()
    cand = Path(env) if env else DEFAULT_VENV_PY
    if cand.is_file():
        return cand
    raise ProviderUnavailable(
        f"no venv interpreter at {cand} — run scripts/setup-avatar-chain.sh")


class ChatterboxVoice:
    """text -> a WAV on disk. Not a base.py ABC: voice is a step inside AvatarProvider."""

    name = "chatterbox"

    def __init__(self, *, voice_ref: Path | None = None, exaggeration: float | None = None,
                 cfg_weight: float | None = None, timeout: int = 1800):
        self.voice_ref = Path(voice_ref) if voice_ref else None
        self.exaggeration = exaggeration
        self.cfg_weight = cfg_weight
        # First call downloads model weights and CPU synthesis is not fast; be patient.
        self.timeout = int(os.environ.get("CHATTERBOX_TIMEOUT", timeout))

    def available(self) -> bool:
        try:
            py = venv_python()
        except ProviderUnavailable:
            return False
        probe = subprocess.run([str(py), "-c", "import chatterbox"],
                               capture_output=True, timeout=120)
        return probe.returncode == 0

    def synthesize(self, text: str, out: Path, *, voice_ref: Path | None = None,
                   rewrite_urls: bool = True) -> Path:
        # A raw domain is the worst thing you can hand a TTS engine — measured 0.592s of
        # hesitation on "appearance-unlimited.com" against 0.000s for the spoken form.
        # See clemtock/speech.py. Opt out with rewrite_urls=False.
        text = speakable(text) if rewrite_urls else text
        text = (text or "").strip()
        if not text:
            raise ProviderUnavailable("nothing to synthesise: empty text")
        ref = Path(voice_ref) if voice_ref else self.voice_ref
        if ref and not ref.is_file():
            raise ProviderUnavailable(f"voice reference not found: {ref}")

        out = Path(out)
        out.parent.mkdir(parents=True, exist_ok=True)
        req = {
            "text": text,
            "out": str(out),
            "ref": str(ref) if ref else None,
            "exaggeration": self.exaggeration,
            "cfg_weight": self.cfg_weight,
        }
        try:
            proc = subprocess.run(
                [str(venv_python()), str(_WORKER)],
                input=json.dumps(req).encode("utf-8"),
                capture_output=True, timeout=self.timeout)
        except subprocess.TimeoutExpired as e:
            raise ProviderUnavailable(
                f"chatterbox timed out after {self.timeout}s (CPU synthesis is slow; "
                f"raise CHATTERBOX_TIMEOUT)") from e

        raw = proc.stdout.decode("utf-8", "replace").strip()
        # The worker prints exactly one JSON object; anything else means it died early.
        try:
            res = json.loads(raw.splitlines()[-1]) if raw else {}
        except (json.JSONDecodeError, IndexError):
            raise ProviderUnavailable(
                f"chatterbox worker returned no JSON (rc={proc.returncode}): "
                f"{proc.stderr.decode('utf-8','replace')[-400:]}") from None

        if not res.get("ok"):
            raise ProviderUnavailable(f"chatterbox failed: {res.get('error','unknown')}")
        if not out.is_file():
            raise ProviderUnavailable(f"chatterbox reported success but {out} is missing")
        return out
