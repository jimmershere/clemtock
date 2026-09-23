"""Chatterbox TTS worker — runs INSIDE the venv, invoked as a subprocess.

clemtock's runtime is deliberately stdlib-only (see config.py); Chatterbox drags in
torch and friends. Rather than make the whole app depend on a 4 GB virtualenv, the
provider shells out to this script with `.venv/bin/python`. The app stays importable
on a box with no venv at all, and a missing model degrades to ProviderUnavailable
instead of an ImportError at startup.

Contract: argv is a single JSON object on stdin, a single JSON object on stdout.

    in : {"text": "...", "out": "/path/voice.wav", "ref": "/path/ref.wav"|null,
          "exaggeration": 0.5, "cfg_weight": 0.5}
    out: {"ok": true, "path": "...", "sample_rate": 24000, "seconds": 3.4}
         {"ok": false, "error": "..."}
"""
from __future__ import annotations

import json
import sys


def main() -> int:
    try:
        req = json.load(sys.stdin)
    except Exception as e:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": f"bad request: {e}"}))
        return 2

    try:
        import torch
        import torchaudio
        from chatterbox.tts import ChatterboxTTS

        # No GPU on either fleet host; be explicit rather than letting it guess.
        device = "cuda" if torch.cuda.is_available() else "cpu"
        model = ChatterboxTTS.from_pretrained(device=device)

        kwargs = {}
        ref = req.get("ref")
        if ref:
            kwargs["audio_prompt_path"] = ref
        for k in ("exaggeration", "cfg_weight"):
            if req.get(k) is not None:
                kwargs[k] = float(req[k])

        wav = model.generate(req["text"], **kwargs)
        out = req["out"]
        torchaudio.save(out, wav, model.sr)
        seconds = float(wav.shape[-1]) / float(model.sr)
        print(json.dumps({"ok": True, "path": out, "sample_rate": int(model.sr),
                          "seconds": round(seconds, 3), "device": device}))
        return 0
    except Exception as e:  # noqa: BLE001
        import traceback
        print(json.dumps({"ok": False, "error": f"{type(e).__name__}: {e}",
                          "trace": traceback.format_exc()[-1500:]}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
