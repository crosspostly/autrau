"""Parakeet v3 provider (NVIDIA, via NeMo toolkit).

Requires NVIDIA GPU + CUDA. Multilingual (25 European languages incl. Russian),
state of the art for 2025-2026.

For CPU-only or non-NVIDIA hardware, prefer faster-whisper or whisper-cpp.

HF model: https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3
NeMo:     pip install -U nemo_toolkit['asr']
"""
from __future__ import annotations

import json
import logging
import os
import urllib.request
from pathlib import Path
from typing import Callable, Optional

from .base import (
    Provider,
    ProviderInfo,
    Segment,
    SegmentCallback,
)
from .faster_whisper import _pip_install

log = logging.getLogger("autrau.parakeet")

_HF_API = "https://huggingface.co/api/models"
_REPO = "nvidia/parakeet-tdt-0.6b-v3"

_PARAKEET_LANGS = [
    "bg", "hr", "cs", "da", "nl", "en", "et", "fi", "fr", "de", "el", "hu",
    "it", "lv", "lt", "mt", "pl", "pt", "ro", "sk", "sl", "es", "sv", "ru", "uk",
    "auto",
]


class ParakeetProvider(Provider):
    info = ProviderInfo(
        name="parakeet",
        display_name="Parakeet TDT v3 (NVIDIA, GPU)",
        description="SOTA 2025-2026. 25 европейских языков + русский. Требует NVIDIA GPU + CUDA.",
        models=["parakeet-tdt-0.6b-v3"],
        default_model="parakeet-tdt-0.6b-v3",
        requires_gpu=True,
        python_deps=["nemo_toolkit[asr]"],
        install_hint="pip install -U nemo_toolkit[asr]",
        homepage="https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3",
        languages=_PARAKEET_LANGS,
    )

    def __init__(self) -> None:
        self._model = None
        self._loaded_model: Optional[str] = None

    # ---- availability ----
    def is_available(self) -> tuple[bool, str]:
        # We import inside to avoid hard dep for users who don't use this provider.
        try:
            import nemo.collections.asr as nemo_asr  # noqa: F401
        except ImportError:
            return False, "nemo_toolkit не установлен. Запустите install."
        # Also check CUDA
        try:
            import torch
            if not torch.cuda.is_available():
                return False, ("nemo_toolkit установлен, но CUDA недоступна. "
                               "Parakeet v3 требует NVIDIA GPU.")
        except ImportError:
            return False, "PyTorch не установлен (нужен для NeMo)."
        return True, ""

    def install(self, on_log: Optional[Callable[[str], None]] = None) -> bool:
        log_cb = on_log or (lambda m: None)
        log_cb("Это тяжёлая установка: PyTorch + nemo_toolkit[asr] (~3-5 ГБ).")
        log_cb("Шаг 1/2: установка nemo_toolkit[asr] …")
        ok = _pip_install(["nemo_toolkit[asr]"], log_cb)
        if not ok:
            return False
        log_cb("OK.")
        return True

    # ---- model mgmt ----
    def list_models(self) -> list[dict]:
        cache = self._hf_cache_dir()
        return [{
            "name": "parakeet-tdt-0.6b-v3",
            "display": "Parakeet TDT 0.6B v3 — 600 М парам, 25 языков (SOTA 2025)",
            "size_mb": 2400,
            "downloaded": cache.exists() and any(cache.rglob("*.nemo")),
            "local_path": str(cache),
            "source_url": f"https://huggingface.co/{_REPO}",
        }]

    def _hf_cache_dir(self) -> Path:
        base = Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface"))
        return base / "hub" / f"models--{_REPO.replace('/', '--')}"

    def is_model_downloaded(self, model: str) -> bool:
        cache = self._hf_cache_dir()
        return cache.exists() and any(cache.rglob("*.nemo"))

    def model_local_path(self, model: str) -> Path:
        return self._hf_cache_dir()

    def check_model_update(self, model: str) -> dict:
        info: dict = {
            "provider": "parakeet",
            "model": model,
            "source": f"https://huggingface.co/{_REPO}",
            "has_update": False,
            "local_exists": self.is_model_downloaded(model),
        }
        try:
            with urllib.request.urlopen(f"{_HF_API}/{_REPO}", timeout=10) as r:
                data = json.loads(r.read().decode("utf-8"))
            info["remote_sha"] = data.get("sha", "")
            info["last_modified"] = data.get("lastModified", "")
        except Exception as e:
            info["error"] = f"Не удалось проверить: {e}"
        return info

    def download_model(
        self,
        model: str,
        on_progress: Optional[Callable[[float, str], None]] = None,
    ) -> Path:
        cb = on_progress or (lambda p, m: None)
        cb(0, f"Качаю {_REPO} с HuggingFace (~2.4 ГБ) …")
        from huggingface_hub import snapshot_download
        path = snapshot_download(repo_id=_REPO)
        cb(100, f"Готово: {path}")
        return Path(path)

    # ---- inference ----
    def load(self, model: str, device: str = "cuda", **kwargs) -> None:
        avail, why = self.is_available()
        if not avail:
            raise RuntimeError(why)
        if self._loaded_model == model and self._model is not None:
            return
        from nemo.collections.asr import models as nemo_asr_models
        log.info("Loading Parakeet %s …", model)
        self._model = nemo_asr_models.ASRModel.from_pretrained(
            model_name=f"nvidia/{model}"
        )
        if device == "cuda":
            try:
                self._model = self._model.cuda()
            except Exception:
                log.warning("Не удалось переместить на CUDA, остаюсь на CPU")
        self._model.eval()
        self._loaded_model = model

    def transcribe(
        self,
        audio_path: Path,
        language: str,
        on_segment: Optional[SegmentCallback] = None,
    ) -> dict:
        if self._model is None:
            raise RuntimeError("Provider not loaded. Call load() first.")

        # NeMo expects 16 kHz mono wav. ffmpeg-side conversion is up to caller
        # (faster-whisper does it internally; here we delegate too).
        out = self._model.transcribe(
            [str(audio_path)],
            timestamps=True,
        )
        hyp = out[0]
        text = getattr(hyp, "text", "")

        segments: list[Segment] = []
        # word-level timestamps if available
        ts = getattr(hyp, "timestamp", None) or {}
        word_ts = ts.get("word", []) if isinstance(ts, dict) else []
        if word_ts:
            # Find total duration for percent
            total_end = max((float(w.get("end", 0)) for w in word_ts), default=0.0)
            current = []
            for w in word_ts:
                seg = Segment(start=float(w.get("start", 0)),
                              end=float(w.get("end", 0)),
                              text=str(w.get("word", "")).strip())
                if seg.text:
                    current.append(seg)
                    if on_segment:
                        pct = int((seg.end / total_end) * 100) if total_end else 0
                        pct = max(0, min(100, pct))
                        on_segment(seg, pct)
            segments = current
        else:
            seg = Segment(start=0.0, end=0.0, text=text)
            segments = [seg]
            if on_segment and text:
                on_segment(seg, 100)

        return {
            "text": text,
            "segments": [s.__dict__ for s in segments],
            "info": {"language": language or "auto"},
        }
