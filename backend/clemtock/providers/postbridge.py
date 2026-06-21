"""Post Bridge publish provider — Phase 7.

Flow:
  1. GET  /v1/social-accounts                      -> connected accounts (id, platform)
  2. POST /v1/media/create-upload-url {mime,size}  -> {media_id, upload_url}
  3. PUT  upload_url  (raw video bytes)             -> uploads the file
  4. POST /v1/posts {caption, social_accounts, media} -> publishes

Publishing is irreversible public posting, so the CLI/UI default to a dry run; the real post
only happens with an explicit execute. Stdlib HTTP only.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path

from .base import ProviderUnavailable

_BASE = "https://api.post-bridge.com"


class PostBridgeProvider:
    name = "post-bridge"

    def __init__(self, api_key: str, timeout: int = 120):
        if not api_key:
            raise ProviderUnavailable("POST_BRIDGE_API_KEY is not set")
        self.api_key = api_key
        self.timeout = timeout

    def _req(self, url: str, body: dict | bytes | None = None, method: str = "GET",
             ctype: str = "application/json", auth: bool = True):
        if isinstance(body, dict):
            data = json.dumps(body).encode()
        else:
            data = body
        headers = {"Content-Type": ctype}
        if auth:
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                raw = r.read()
                return json.loads(raw) if raw and ctype == "application/json" else raw
        except urllib.error.HTTPError as e:
            raise ProviderUnavailable(f"post-bridge HTTP {e.code}: {e.read().decode('utf-8','replace')[:300]}") from e
        except urllib.error.URLError as e:
            raise ProviderUnavailable(f"post-bridge unreachable: {e.reason}") from e

    def accounts(self) -> list[dict]:
        return (self._req(f"{_BASE}/v1/social-accounts").get("data") or [])

    def resolve(self, names: list[str]) -> list[int]:
        """Map platform names or ids to account ids."""
        accts = self.accounts()
        by_platform = {a.get("platform"): a.get("id") for a in accts}
        ids = {str(a.get("id")): a.get("id") for a in accts}
        out = []
        for n in names:
            n = n.strip()
            if n in by_platform:
                out.append(by_platform[n])
            elif n in ids:
                out.append(ids[n])
        return out

    def publish(self, video: Path, caption: str, account_ids: list[int]) -> dict:
        if not account_ids:
            raise ProviderUnavailable("no matching social accounts to publish to")
        size = video.stat().st_size
        up = self._req(f"{_BASE}/v1/media/create-upload-url", method="POST", body={
            "mime_type": "video/mp4", "size_bytes": size, "name": video.name})
        media_id, upload_url = up.get("media_id"), up.get("upload_url")
        if not (media_id and upload_url):
            raise ProviderUnavailable(f"create-upload-url gave no media_id/upload_url: {up}")
        # PUT raw bytes to the signed URL (no auth header on the storage URL)
        self._req(upload_url, body=video.read_bytes(), method="PUT", ctype="video/mp4", auth=False)
        post = self._req(f"{_BASE}/v1/posts", method="POST", body={
            "caption": caption, "social_accounts": account_ids, "media": [media_id]})
        return {"media_id": media_id, "post": post, "accounts": account_ids}
