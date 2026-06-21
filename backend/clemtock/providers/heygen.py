"""HeyGen AvatarProvider — script text -> talking-head video with a (cloned) voice.

Flow:
  1. POST /v2/video/generate   (avatar_id + voice text) -> video_id
  2. poll GET /v1/video_status.get?video_id=...         -> status completed, video_url
  3. download to disk

Uses the account's existing avatar + cloned voice ids (from the vault). Stdlib HTTP only.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path

from .base import AvatarProvider, ProviderUnavailable

_GENERATE = "https://api.heygen.com/v2/video/generate"
_STATUS = "https://api.heygen.com/v1/video_status.get"


class HeyGenAvatarProvider(AvatarProvider):
    name = "heygen"

    def __init__(self, api_key: str, avatar_id: str = "", voice_id: str = "",
                 width: int = 720, height: int = 1280,
                 poll_timeout: int = 600, poll_every: int = 8):
        if not api_key:
            raise ProviderUnavailable("HEYGEN_API_KEY is not set")
        self.api_key = api_key
        self.avatar_id = avatar_id
        self.voice_id = voice_id
        self.width, self.height = width, height
        self.poll_timeout = poll_timeout
        self.poll_every = poll_every

    def _req(self, url: str, body: dict | None = None, method: str = "POST", timeout: int = 60):
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(url, data=data, method=method, headers={
            "X-Api-Key": self.api_key, "Content-Type": "application/json", "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise ProviderUnavailable(f"HeyGen HTTP {e.code}: {e.read().decode('utf-8','replace')[:300]}") from e
        except urllib.error.URLError as e:
            raise ProviderUnavailable(f"HeyGen unreachable: {e.reason}") from e

    def generate(self, text: str, out: Path, *, avatar_id: str | None = None,
                 voice_id: str | None = None) -> Path:
        avatar = avatar_id or self.avatar_id
        voice = voice_id or self.voice_id
        if not avatar:
            raise ProviderUnavailable("HeyGen needs an avatar_id (HEYGEN_CARTOON_AVATAR_ID)")
        resp = self._req(_GENERATE, {
            "video_inputs": [{
                "character": {"type": "avatar", "avatar_id": avatar, "avatar_style": "normal"},
                "voice": {"type": "text", "input_text": text, "voice_id": voice},
            }],
            "dimension": {"width": self.width, "height": self.height},
        })
        if resp.get("error"):
            raise ProviderUnavailable(f"HeyGen generate error: {json.dumps(resp['error'])[:300]}")
        video_id = (resp.get("data") or {}).get("video_id")
        if not video_id:
            raise ProviderUnavailable(f"HeyGen returned no video_id: {json.dumps(resp)[:300]}")

        deadline = time.monotonic() + self.poll_timeout
        while time.monotonic() < deadline:
            time.sleep(self.poll_every)
            st = self._req(f"{_STATUS}?video_id={video_id}", method="GET")
            data = st.get("data") or {}
            status = data.get("status")
            if status == "completed":
                url = data.get("video_url")
                if not url:
                    raise ProviderUnavailable(f"HeyGen completed but no video_url: {json.dumps(data)[:300]}")
                out.parent.mkdir(parents=True, exist_ok=True)
                with urllib.request.urlopen(url, timeout=180) as r:
                    out.write_bytes(r.read())
                return out
            if status in ("failed", "error"):
                raise ProviderUnavailable(f"HeyGen video failed: {json.dumps(data)[:300]}")
        raise ProviderUnavailable(f"HeyGen video {video_id} timed out after {self.poll_timeout}s")
