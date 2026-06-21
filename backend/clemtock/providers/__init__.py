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

__all__ = [
    "ProviderUnavailable",
    "ScriptProvider",
    "ImageProvider",
    "VideoProvider",
    "AvatarProvider",
]
