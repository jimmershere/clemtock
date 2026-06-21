"""kie.ai image-to-video VideoProvider.

Flow (kie unified Jobs API):
  1. upload the seed image (base64)         -> public temp URL (3-day retention)
  2. POST /api/v1/jobs/createTask           -> taskId
  3. poll GET /api/v1/jobs/recordInfo       -> state success, resultJson.resultUrls[0]
  4. download the result video to disk

Seed image is required: image_urls must be a public URL, so we use kie's own uploader
(no LAN/public hosting of the user's file needed). Stdlib HTTP only.
"""
from __future__ import annotations

import base64
import json
import mimetypes
import socket
import time
import urllib.error
import urllib.request
from pathlib import Path

from .base import ProviderUnavailable, VideoProvider

_orig_getaddrinfo = socket.getaddrinfo


def _force_ipv4() -> None:
    """kie API keys are IP-whitelisted on the IPv4 egress; api.kie.ai also has AAAA records,
    so default resolution picks IPv6 (not whitelisted) and gets rejected. Pin to IPv4."""
    def gai(host, port, family=0, *args, **kwargs):
        res = _orig_getaddrinfo(host, port, family, *args, **kwargs)
        v4 = [r for r in res if r[0] == socket.AF_INET]
        return v4 or res
    socket.getaddrinfo = gai

_UPLOAD = "https://kieai.redpandaai.co/api/file-base64-upload"
_CREATE = "https://api.kie.ai/api/v1/jobs/createTask"
_RECORD = "https://api.kie.ai/api/v1/jobs/recordInfo"
# api.kie.ai is behind Cloudflare, which bot-blocks the default Python-urllib UA (error 1010).
_UA = "Mozilla/5.0 (X11; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0"


def _looks_url(v) -> bool:
    return isinstance(v, str) and v.startswith("http")


def _find_url(obj):
    """Defensively locate the first http(s) URL anywhere in a decoded JSON value."""
    if _looks_url(obj):
        return obj
    if isinstance(obj, dict):
        for v in obj.values():
            u = _find_url(v)
            if u:
                return u
    if isinstance(obj, list):
        for v in obj:
            u = _find_url(v)
            if u:
                return u
    return None


class KieVideoProvider(VideoProvider):
    name = "kie"

    def __init__(self, api_key: str, model: str = "kling-2.6/image-to-video",
                 poll_timeout: int = 420, poll_every: int = 6):
        if not api_key:
            raise ProviderUnavailable("KIEAI_API_KEY is not set")
        _force_ipv4()
        self.api_key = api_key
        self.model = model
        self.poll_timeout = poll_timeout
        self.poll_every = poll_every

    def _req(self, url: str, body: dict | None = None, method: str = "POST", timeout: int = 60):
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(url, data=data, method=method, headers={
            "Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json",
            "User-Agent": _UA, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise ProviderUnavailable(f"kie HTTP {e.code}: {e.read().decode('utf-8','replace')[:300]}") from e
        except urllib.error.URLError as e:
            raise ProviderUnavailable(f"kie unreachable: {e.reason}") from e

    def _upload(self, image: Path) -> str:
        mime = mimetypes.guess_type(str(image))[0] or "image/png"
        b64 = base64.b64encode(image.read_bytes()).decode("ascii")
        resp = self._req(_UPLOAD, {
            "base64Data": f"data:{mime};base64,{b64}",
            "uploadPath": "clemtock/seeds",
            "fileName": image.name,
        })
        url = _find_url(resp.get("data", resp))
        if not url:
            raise ProviderUnavailable(f"kie upload returned no URL: {json.dumps(resp)[:300]}")
        return url

    def generate(self, prompt: str, out: Path, *, seconds: float = 5.0,
                 aspect: str = "9:16", seed_image: Path | None = None) -> Path:
        if not seed_image:
            raise ProviderUnavailable("kie image-to-video requires a seed_image")
        # accept a public URL directly; otherwise upload the local file to kie's CDN
        image_url = str(seed_image) if _looks_url(str(seed_image)) else self._upload(Path(seed_image))
        create = self._req(_CREATE, {
            "model": self.model,
            "input": {
                "prompt": prompt,
                "image_urls": [image_url],
                "sound": False,
                "duration": "10" if seconds > 7 else "5",
            },
        })
        task_id = (create.get("data") or {}).get("taskId") or create.get("taskId")
        if not task_id:
            raise ProviderUnavailable(f"kie createTask gave no taskId: {json.dumps(create)[:300]}")

        deadline = time.monotonic() + self.poll_timeout
        while time.monotonic() < deadline:
            time.sleep(self.poll_every)
            rec = self._req(f"{_RECORD}?taskId={task_id}", method="GET")
            data = rec.get("data") or {}
            state = data.get("state")
            if state == "success":
                result = json.loads(data.get("resultJson") or "{}")
                url = (result.get("resultUrls") or [None])[0] or _find_url(result)
                if not url:
                    raise ProviderUnavailable(f"kie success but no resultUrls: {data.get('resultJson')}")
                out.parent.mkdir(parents=True, exist_ok=True)
                dl = urllib.request.Request(url, headers={"User-Agent": _UA})
                with urllib.request.urlopen(dl, timeout=180) as r:
                    out.write_bytes(r.read())
                return out
            if state == "fail":
                raise ProviderUnavailable(f"kie task failed: {json.dumps(data)[:300]}")
        raise ProviderUnavailable(f"kie task {task_id} timed out after {self.poll_timeout}s")
