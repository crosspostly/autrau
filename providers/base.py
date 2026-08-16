"""Provider base class + registry.

A `Provider` is one back-end for speech-to-text (faster-whisper, whisper.cpp,
Parakeet v3, ...). All providers expose the same interface so the server and
UI can switch between them without changes elsewhere.
"""
from __future__ import annotations

import abc
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Optional

log = logging.getLogger("autrau.providers")

# Path that holds downloaded model artifacts.
# Resolved at import time from the project root.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MODELS_DIR = _PROJECT_ROOT / "data" / "models"
DEFAULT_MODELS_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class ProviderInfo:
    """Static metadata for a provider. Surfaced to the UI."""

    name: str                          # "faster-whisper"
    display_name: str                  # "Faster-Whisper (CTranslate2)"
    description: str
    models: list[str]                  # ["tiny", "base", "small", ...]
    default_model: str
    requires_gpu: bool = False
    python_deps: list[str] = field(default_factory=list)
    install_hint: str = ""             # pip one-liner
    homepage: str = ""
    languages: list[str] = field(default_factory=list)  # ["ru","en",...] or ["auto"]


@dataclass
class Segment:
    start: float
    end: float
    text: str


# A callback fired by transcribe() for every recognized segment.
# The provider supplies a percent (0-100) so the UI doesn't have to know
# about audio duration internals.
SegmentCallback = Callable[[Segment, int], None]


class Provider(abc.ABC):
    """Abstract base for all transcription providers."""

    info: ProviderInfo

    # ---- introspection ----
    @abc.abstractmethod
    def is_available(self) -> tuple[bool, str]:
        """Return (True, "") if the provider is ready to load models.
        Otherwise (False, "human-readable reason")."""

    @abc.abstractmethod
    def install(self, on_log: Optional[Callable[[str], None]] = None) -> bool:
        """Best-effort install. Returns True on success."""

    # ---- model management ----
    @abc.abstractmethod
    def list_models(self) -> list[dict]:
        """List models with availability info.
        Each dict: {name, display, size_mb, downloaded, latest_sha, source_url}"""

    @abc.abstractmethod
    def is_model_downloaded(self, model: str) -> bool:
        ...

    @abc.abstractmethod
    def download_model(
        self,
        model: str,
        on_progress: Optional[Callable[[float, str], None]] = None,
    ) -> Path:
        """Download the model. Returns local path."""

    @abc.abstractmethod
    def check_model_update(self, model: str) -> dict:
        """Return {latest, local, has_update, info_url} from official source."""

    # ---- inference ----
    @abc.abstractmethod
    def load(self, model: str, device: str = "cpu", **kwargs) -> None:
        """Load the model into memory. Idempotent if same model+device."""

    @abc.abstractmethod
    def transcribe(
        self,
        audio_path: Path,
        language: str,
        on_segment: Optional[SegmentCallback] = None,
    ) -> dict:
        """Run transcription. Returns {"text": str, "segments": [...], "info": {...}}."""


class ProviderRegistry:
    """Holds a singleton instance of each provider class."""

    def __init__(self) -> None:
        self._providers: dict[str, Provider] = {}

    def register(self, provider: Provider) -> None:
        self._providers[provider.info.name] = provider

    def get(self, name: str) -> Provider:
        if name not in self._providers:
            raise KeyError(f"Unknown provider: {name}. "
                           f"Available: {list(self._providers)}")
        return self._providers[name]

    def all(self) -> Iterable[Provider]:
        return self._providers.values()

    def names(self) -> list[str]:
        return list(self._providers.keys())


registry = ProviderRegistry()
