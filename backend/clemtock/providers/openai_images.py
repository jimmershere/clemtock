"""OpenAI gpt-image-1 ImageProvider — prompt -> still PNG.

"ChatGPT makes great images." Returns base64 PNG which we write to disk. Stdlib HTTP.
"""
from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from pathlib import Path

from .base import ImageProvider, ProviderUnavailable

_ENDPOINT = "https://api.openai.com/v1/images/generations"
_SIZES = {"9:16": "1024x1536", "16:9": "1536x1024", "1:1": "1024x1024"}


class OpenAIImageProvider(ImageProvider):
    name = "gpt-image-1"

    def __init__(self, api_key: str, model: str = "gpt-image-1", timeout: int = 180):
        if not api_key:
            raise ProviderUnavailable("OPENAI_API_KEY is not set")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def generate(self, prompt: str, out: Path, *, size: str = "1024x1536") -> Path:
        size = _SIZES.get(size, size)  # accept "9:16" or a literal WxH
        body = json.dumps({
            "model": self.model, "prompt": prompt, "size": size, "n": 1,
        }).encode("utf-8")
        req = urllib.request.Request(_ENDPOINT, data=body, method="POST", headers={
            "Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json",
        })
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:400]
            raise ProviderUnavailable(f"gpt-image-1 HTTP {e.code}: {detail}") from e
        except urllib.error.URLError as e:
            raise ProviderUnavailable(f"OpenAI unreachable: {e.reason}") from e

        b64 = payload["data"][0]["b64_json"]
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(base64.b64decode(b64))
        return out
