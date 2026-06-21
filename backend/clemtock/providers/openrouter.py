"""OpenRouter-backed ScriptProvider: brief -> ad-script.json.

Routes to a strong instruction-following model (default Claude Sonnet 4.5) and asks it to
emit an object conforming to schema/ad-script.schema.json. Stdlib-only HTTP (urllib).
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from .base import ProviderUnavailable, ScriptProvider

_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"

_SYSTEM = """You are clemtock's ad director. Turn the user's brief and asset manifest into
a single JSON object conforming to the clemtock ad-script schema (version 1). Rules:
- Output ONLY the JSON object, no prose, no markdown fences.
- canvas is 1080x1920, fps 30. Fill `duration` to match the brief (default 15s).
- Build 4-7 `scenes`, each with id, start, end (contiguous, covering 0..duration), and a
  `template` from: title, photo, video, terminal, split, cta.
- `copy` MUST be an object with string keys from: kicker, headline, sub, cta (use \n inside a
  value for line breaks). NEVER make `copy` a bare string.
- A scene references images via `assets`: an ARRAY of asset ids (e.g. "assets": ["hero"]).
  NEVER use `asset`, `assetId`, or `image` — always the `assets` array.
- Reference the provided uploaded assets by their exact ids (do not invent new ids for them).
  If the brief needs a visual no upload covers, add an entry to top-level `assets` with
  source:"gen", a `provider` (gpt-image-1 for stills, kie for motion, heygen for a
  spokesperson), and a `prompt`, then reference that id in a scene's `assets`.
- Keep copy punchy and ad-appropriate. End on a `cta` scene.
- Provide a `palette` of hex colors that fits the brief's tone."""


class OpenRouterScriptProvider(ScriptProvider):
    name = "openrouter"

    def __init__(self, api_key: str, model: str = "anthropic/claude-sonnet-4.5",
                 timeout: int = 120, max_tokens: int = 4000):
        if not api_key:
            raise ProviderUnavailable("OPENROUTER_API_KEY is not set")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        # an ad-script JSON is small; cap completion so OpenRouter doesn't reserve the
        # model's full context (which can trip a 402 on credit-limited keys)
        self.max_tokens = int(os.environ.get("CLEMTOCK_SCRIPT_MAX_TOKENS", max_tokens))

    def generate(self, brief: str, assets: dict, duration: float) -> dict:
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
            "response_format": {"type": "json_object"},
            "temperature": 0.7,
            "max_tokens": self.max_tokens,
        }).encode("utf-8")

        req = urllib.request.Request(
            _ENDPOINT, data=body, method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "X-Title": "clemtock",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:400]
            raise ProviderUnavailable(f"OpenRouter HTTP {e.code}: {detail}") from e
        except urllib.error.URLError as e:
            raise ProviderUnavailable(f"OpenRouter unreachable: {e.reason}") from e

        content = payload["choices"][0]["message"]["content"]
        return _parse_script(content)


def _parse_script(content: str) -> dict:
    """Extract the JSON object from a model response, tolerating stray fences."""
    content = content.strip()
    if content.startswith("```"):
        content = content.split("```", 2)[1]
        if content.startswith("json"):
            content = content[4:]
    start, end = content.find("{"), content.rfind("}")
    if start == -1 or end == -1:
        raise ProviderUnavailable("model did not return a JSON object")
    return json.loads(content[start : end + 1])
