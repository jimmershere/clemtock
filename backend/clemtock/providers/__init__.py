"""Provider layer: one interface per modality, swappable implementations.

Interfaces live in `base`; concrete providers register against them. A provider that has
no working key raises `ProviderUnavailable` rather than pretending to succeed.
"""
from .base import (
    ProviderUnavailable,
    ScriptProvider,
    ImageProvider,
    VideoProvider,
    AvatarProvider,
)

from .ollama_script import OllamaScriptProvider
from .vast_gpu import VastGPU, VastError

__all__ = [
    "ProviderUnavailable",
    "OllamaScriptProvider",
    "VastGPU",
    "VastError",
    "ScriptProvider",
    "ImageProvider",
    "VideoProvider",
    "AvatarProvider",
]
