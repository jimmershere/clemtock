"""Ollama-backed ScriptProvider: brief -> ad-script.json, entirely on this host.

Same contract and same system prompt as the OpenRouter provider — only the transport
differs — so an ad script is identical in shape whichever brain wrote it. Importing
`_SYSTEM` rather than copying it means the schema rules cannot drift between the two.

Why this exists: neither fleet host has a discrete GPU, but ad copy is short and a 4-9B
model at Q4 runs fine on pop-os CPU (~10-15 tok/s). That removes the OpenRouter key from
the critical path and costs nothing per script. See
/app/portrender/docs/local-ai-options.md.

Quality caveat, stated plainly: a local 4-9B model writes weaker copy than Claude. For
work a human will actually ship, prefer a Claude Code skill (fleet rule 1 — the thinking
belongs in the agent, not in app code). This provider is for unattended runs: cron, batch,
and anything that must not block on a paid API.

Stdlib-only HTTP, matching the rest of the provider layer.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from .base import ProviderUnavailable, ScriptProvider
from .openrouter import _SYSTEM, _parse_script

DEFAULT_HOST = "http://127.0.0.1:11434"
DEFAULT_MODEL = "qwen3:8b"


class OllamaScriptProvider(ScriptProvider):
    name = "ollama"

    def __init__(self, model: str = "", host: str = "", timeout: int = 600,
                 num_predict: int = 4000, temperature: float = 0.7):
        self.host = (host or os.environ.get("OLLAMA_HOST") or DEFAULT_HOST).rstrip("/")
        if not self.host.startswith("http"):          # OLLAMA_HOST is often "host:port"
            self.host = "http://" + self.host
        self.model = model or os.environ.get("CLEMTOCK_OLLAMA_MODEL") or DEFAULT_MODEL
        # CPU inference is slow: a 15s ad script is ~1-2k tokens, so allow minutes.
        self.timeout = int(os.environ.get("CLEMTOCK_OLLAMA_TIMEOUT", timeout))
        self.num_predict = num_predict
        self.temperature = temperature

    # ---------- health ----------
    def available(self) -> bool:
        """True when the daemon answers and the configured model is pulled."""
        try:
            return self.model in self.installed_models()
        except ProviderUnavailable:
            return False

    def installed_models(self) -> list[str]:
        try:
            with urllib.request.urlopen(self.host + "/api/tags", timeout=10) as r:
                tags = json.loads(r.read().decode("utf-8"))
        except urllib.error.URLError as e:
            raise ProviderUnavailable(
                f"ollama unreachable at {self.host} ({e.reason}) — "
                f"start it with `systemctl --user start ollama` or `ollama serve`") from e
        except OSError as e:
            raise ProviderUnavailable(f"ollama unreachable at {self.host}: {e}") from e
        return [m.get("name", "") for m in tags.get("models", [])]

    # ---------- generation ----------
    def generate(self, brief: str, assets: dict, duration: float) -> dict:
        installed = self.installed_models()
        if self.model not in installed:
            raise ProviderUnavailable(
                f"ollama has no model {self.model!r} (installed: {', '.join(installed) or 'none'}) — "
                f"pull it with `ollama pull {self.model}`")

        user = json.dumps({
            "brief": brief,
            "duration_seconds": duration,
            "uploaded_assets": assets,
        }, indent=2)
        body = json.dumps({
            "model": self.model,
            "messages": [
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "format": "json",          # ollama's JSON mode; still parsed defensively below
            "options": {
                "temperature": self.temperature,
                "num_predict": self.num_predict,
            },
        }).encode("utf-8")

        req = urllib.request.Request(
            self.host + "/api/chat", data=body, method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:400]
            raise ProviderUnavailable(f"ollama HTTP {e.code}: {detail}") from e
        except urllib.error.URLError as e:
            raise ProviderUnavailable(f"ollama unreachable: {e.reason}") from e

        content = (payload.get("message") or {}).get("content", "")
        if not content:
            raise ProviderUnavailable(f"ollama returned no content: {str(payload)[:200]}")
        # Reasoning models (qwen3) may emit <think>…</think> ahead of the JSON;
        # _parse_script slices from the first { to the last }, which drops it.
        return _parse_script(content)
