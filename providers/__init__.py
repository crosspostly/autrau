"""Provider registry — auto-registers all built-in providers on import."""
from __future__ import annotations

from .base import Provider, ProviderInfo, Segment, registry
from .faster_whisper import FasterWhisperProvider
from .whisper_cpp import WhisperCppProvider
from .parakeet import ParakeetProvider

# Auto-register on import. Order = display order in UI.
registry.register(FasterWhisperProvider())
registry.register(WhisperCppProvider())
registry.register(ParakeetProvider())

__all__ = [
    "Provider",
    "ProviderInfo",
    "Segment",
    "registry",
    "FasterWhisperProvider",
    "WhisperCppProvider",
    "ParakeetProvider",
]
