"""HeyGen AvatarProvider — script text -> talking-head video with a (cloned) voice.

Flow:
  1. POST /v2/video/generate   (avatar_id + voice text) -> video_id
  2. poll GET /v1/video_status.get?video_id=...         -> status completed, video_url
  3. download to disk

Uses the account's existing avatar + cloned voice ids (from the vault). Stdlib HTTP only.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

from .base import AvatarProvider, ProviderUnavailable

# v3. The v2 generate call and v1 status call both carried a Legacy warning naming a
# 2026-10-31 sunset; migrated 2026-09-24 and the schema confirmed against the live API.
#
# v3 is simpler than v2: a flat body instead of video_inputs[].character, and a
# talking_photo_id goes straight into `avatar_id` — there is no separate field for it.
#   POST /v3/videos {type, avatar_id, script, voice_id} -> {data:{video_id, status}}
#   GET  /v3/videos/{id} -> {data:{status, video_url, thumbnail_url, gif_url, duration,…}}
_GENERATE = "https://api.heygen.com/v3/videos"
_STATUS = "https://api.heygen.com/v3/videos/"
_ME = "https://api.heygen.com/v3/users/me"
_UPLOAD_TALKING_PHOTO = "https://upload.heygen.com/v1/talking_photo"

# NOTE (verified 2026-09-23): /v2/video/generate returns a Legacy warning naming a
# **2026-10-31 sunset** and pointing at the v3 API. Not just the quota endpoint — the
# generate call itself. DONE — migrated 2026-09-24, see the v3 note above.

# The account has auto-reload enabled ($75 recharged whenever the wallet drops below
# $5), and HeyGen exposes no API to change that — it is dashboard-only. So the wallet
# is not a budget, it is a tap. Refuse to generate once the balance nears the trigger,
# or an unattended pipeline will quietly re-bill the card forever. See issue PR-13.
DEFAULT_MIN_BALANCE_USD = 10.0


class HeyGenAvatarProvider(AvatarProvider):
    name = "heygen"

    def __init__(self, api_key: str, avatar_id: str = "", voice_id: str = "",
                 talking_photo_id: str = "",
                 width: int = 720, height: int = 1280,
                 poll_timeout: int = 600, poll_every: int = 8):
        if not api_key:
            raise ProviderUnavailable("HEYGEN_API_KEY is not set")
        self.api_key = api_key
        self.avatar_id = avatar_id
        self.voice_id = voice_id
        self.talking_photo_id = talking_photo_id or os.environ.get("HEYGEN_TALKING_PHOTO_ID", "")
        self.width, self.height = width, height
        self.poll_timeout = poll_timeout
        self.poll_every = poll_every
        self.min_balance = float(os.environ.get("HEYGEN_MIN_BALANCE_USD",
                                                DEFAULT_MIN_BALANCE_USD))
        # v3 takes aspect_ratio/resolution rather than an explicit pixel dimension.
        self.aspect_ratio = os.environ.get("HEYGEN_ASPECT_RATIO", "9:16")
        self.resolution = os.environ.get("HEYGEN_RESOLUTION", "1080p")
        self.last_video_id: str | None = None
        self.last_meta: dict = {}

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

    def balance(self) -> float:
        """Wallet balance in USD. Read-only; HeyGen has no billing write API."""
        me = self._req(_ME, method="GET")
        wallet = ((me.get("data") or {}).get("wallet") or {})
        return float(wallet.get("remaining_balance") or 0.0)

    def check_budget(self) -> float:
        """Raise unless the wallet is comfortably above the auto-reload trigger."""
        bal = self.balance()
        if bal <= self.min_balance:
            raise ProviderUnavailable(
                f"HeyGen wallet ${bal:.2f} is at or below the ${self.min_balance:.2f} floor. "
                f"Auto-reload would recharge the card rather than stopping — refusing. "
                f"Raise HEYGEN_MIN_BALANCE_USD deliberately, or top up by hand.")
        return bal

    def upload_talking_photo(self, image: Path) -> str:
        """Upload a character picture and get an id you can drive with speech.

        This is the path that matters for cartoon brands: HeyGen's 1,264 stock avatars
        are all photoreal presenters, so the only way to animate *your* character is to
        hand it one. Works on illustrated art — verified on a 768x768 portrait crop.

        Feed it a head-and-shoulders crop on a solid background, not a full-body figure:
        it is a face model, and a face occupying a sixth of the frame gives it little to
        work with.
        """
        image = Path(image)
        if not image.is_file():
            raise ProviderUnavailable(f"no such image: {image}")
        data = image.read_bytes()
        ctype = "image/jpeg" if image.suffix.lower() in (".jpg", ".jpeg") else "image/png"
        req = urllib.request.Request(_UPLOAD_TALKING_PHOTO, data=data, method="POST",
                                     headers={"X-Api-Key": self.api_key, "Content-Type": ctype})
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                resp = json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise ProviderUnavailable(
                f"HeyGen upload HTTP {e.code}: {e.read().decode('utf-8','replace')[:300]}") from e
        tp = (resp.get("data") or {}).get("talking_photo_id")
        if not tp:
            raise ProviderUnavailable(f"HeyGen upload returned no id: {json.dumps(resp)[:300]}")
        return tp

    def generate(self, text: str, out: Path, *, avatar_id: str | None = None,
                 voice_id: str | None = None, talking_photo_id: str | None = None) -> Path:
        self.check_budget()
        voice = voice_id or self.voice_id
        tp = talking_photo_id or self.talking_photo_id
        avatar = avatar_id or self.avatar_id
        if tp:
            character = {"type": "talking_photo", "talking_photo_id": tp}
        elif avatar:
            character = {"type": "avatar", "avatar_id": avatar, "avatar_style": "normal"}
        else:
            raise ProviderUnavailable(
                "HeyGen needs either a talking_photo_id (your own character) or an "
                "avatar_id (a stock presenter)")
        body = {
            "type": "avatar",
            "avatar_id": character["talking_photo_id"] if character["type"] == "talking_photo"
                         else character["avatar_id"],
            "script": text,
            "voice_id": voice,
            "aspect_ratio": self.aspect_ratio,
            "resolution": self.resolution,
        }
        resp = self._req(_GENERATE, body)
        if resp.get("error"):
            raise ProviderUnavailable(f"HeyGen generate error: {json.dumps(resp['error'])[:300]}")
        video_id = (resp.get("data") or {}).get("video_id")
        self.last_video_id = video_id
        if not video_id:
            raise ProviderUnavailable(f"HeyGen returned no video_id: {json.dumps(resp)[:300]}")

        deadline = time.monotonic() + self.poll_timeout
        while time.monotonic() < deadline:
            time.sleep(self.poll_every)
            st = self._req(f"{_STATUS}{video_id}", method="GET")
            data = st.get("data") or {}
            status = data.get("status")
            if status == "completed":
                # v3 hands back more than v2 did; the review UI wants all of it.
                self.last_meta = {k: data.get(k) for k in
                                  ("duration", "thumbnail_url", "gif_url", "video_page_url")}
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
