"""Provider interfaces — one per modality.

Implementations live alongside this module (openrouter.py, etc.). Keeping the interfaces
abstract is what lets video-gen swap between kie.ai and HeyGen, or a future Veo/Runway,
without touching the pipeline.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class ProviderUnavailable(RuntimeError):
    """Raised when a provider is asked to work but has no key / is unreachable.

    Honesty over magic: callers surface this rather than silently producing nothing.
    """


class ScriptProvider(ABC):
    """brief (prompt + asset manifest) -> ad-script.json dict."""

    name: str = "script"

    @abstractmethod
    def generate(self, brief: str, assets: dict, duration: float) -> dict:
        ...


class ImageProvider(ABC):
    """prompt -> still image written to `out`. Returns the path written."""

    name: str = "image"

    @abstractmethod
    def generate(self, prompt: str, out: Path, *, size: str = "1024x1536") -> Path:
        ...


class VideoProvider(ABC):
    """prompt (and/or seed image) -> short video clip. Returns the path written."""

    name: str = "video"

    @abstractmethod
    def generate(self, prompt: str, out: Path, *, seconds: float = 4.0,
                 aspect: str = "9:16", seed_image: Path | None = None) -> Path:
        ...


class AvatarProvider(ABC):
    """script text -> talking-head video with a (cloned) voice. Returns the path written."""

    name: str = "avatar"

    @abstractmethod
    def generate(self, text: str, out: Path, *, avatar_id: str | None = None,
                 voice_id: str | None = None) -> Path:
        ...
