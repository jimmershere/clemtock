"""Provider configuration, read from process environment.

No secret is stored by clemtock; this module only *reads* env vars assembled at runtime
by scripts/load-env.sh. `available()` lets the CLI degrade honestly when a key is missing.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    # script brain (LLM -> ad-script.json), via OpenRouter
    openrouter_key: str = ""
    script_model: str = "anthropic/claude-sonnet-4.5"

    # stills
    openai_key: str = ""            # gpt-image-1
    image_model: str = "black-forest-labs/flux-schnell"  # OpenRouter fallback

    # video clips
    kie_key: str = ""
    kie_model: str = "flux-kontext-pro"             # image-edit model (KIEAI_MODEL)
    kie_video_model: str = "kling-2.6/image-to-video"  # image-to-video model

    # spokesperson + voice-over
    heygen_key: str = ""
    heygen_voice_id: str = ""
    heygen_avatar_id: str = ""

    # publishing
    postbridge_key: str = ""

    # ffmpeg host
    floor2_host: str = "floor2"

    @classmethod
    def from_env(cls) -> "Config":
        e = os.environ.get
        return cls(
            openrouter_key=e("OPENROUTER_API_KEY", ""),
            script_model=e("CLEMTOCK_SCRIPT_MODEL", "anthropic/claude-sonnet-4.5"),
            openai_key=e("OPENAI_API_KEY", ""),
            image_model=e("OPENROUTER_IMAGE_MODEL", "black-forest-labs/flux-schnell"),
            kie_key=e("KIEAI_API_KEY", ""),
            kie_model=e("KIEAI_MODEL", "flux-kontext-pro"),
            kie_video_model=e("CLEMTOCK_KIE_VIDEO_MODEL", "kling-2.6/image-to-video"),
            heygen_key=e("HEYGEN_API_KEY", ""),
            heygen_voice_id=e("HEYGEN_VOICE_CLONE_ID", ""),
            heygen_avatar_id=e("HEYGEN_CARTOON_AVATAR_ID", ""),
            postbridge_key=e("POST_BRIDGE_API_KEY", ""),
            floor2_host=e("CLEMTOCK_FLOOR2_HOST", "floor2"),
        )

    def available(self) -> dict[str, bool]:
        """Which capabilities have a key present (not validated — see probe-providers.sh)."""
        return {
            "script": bool(self.openrouter_key),
            "image": bool(self.openai_key or self.openrouter_key),
            "video": bool(self.kie_key),
            "avatar": bool(self.heygen_key),
        }
