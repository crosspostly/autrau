"""Parakeet TDT v3 provider via ONNX Runtime + DirectML.

Uses the community ONNX export of NVIDIA Parakeet TDT 0.6B v3
(multilingual, 25 European languages incl. Russian) with the lightweight
`onnx-asr` package and `onnxruntime-directml`:

  * DirectML EP (DirectX) — runs on ANY GPU (AMD/Intel/NVIDIA), no CUDA needed;
  * CPU fallback built in (slow, but works).

Unlike the NeMo-based `parakeet` provider this does NOT require NVIDIA GPU.
Int8 quantized weights (~640 MB total download).

Model: https://huggingface.co/istupakov/parakeet-tdt-0.6b-v3-onnx
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable, Optional

import numpy as np

from .base import (
    Provider,
    ProviderInfo,
    Segment,
    SegmentCallback,
)
from .faster_whisper import _pip_install

log = logging.getLogger("autrau.parakeet_onnx")

_HF_REPO = "istupakov/parakeet-tdt-0.6b-v3-onnx"
_ASR_NAME = "nemo-parakeet-tdt-0.6b-v3"   # model id used by onnx-asr
_MODEL_NAME = "parakeet-tdt-0.6b-v3"
_QUANT = "int8"                            # int8 encoder: 622 MB, fast on CPU too
_SAMPLE_RATE = 16000

_DOWNLOAD_PATTERNS = [
    "encoder-model.int8.onnx",
    "decoder_joint-model.int8.onnx",
    "nemo128.onnx",
    "vocab.txt",
    "config.json",
    "README.md",
]

_MODEL_LANGS = [
    "bg", "hr", "cs", "da", "nl", "en", "et", "fi", "fr", "de", "el", "hu",
    "it", "lv", "lt", "mt", "pl", "pt", "ro", "sk", "sl", "es", "sv", "ru", "uk",
    "auto",
]


class ParakeetOnnxProvider(Provider):
    info = ProviderInfo(
        name="parakeet-onnx",
        display_name="Parakeet v3 (ONNX/DirectML)",
        description=("SOTA 2025-2026, 25 языков + русский. Работает на любом GPU "
                     "через DirectX (без CUDA) или на CPU."),
        models=[_MODEL_NAME],
        default_model=_MODEL_NAME,
        requires_gpu=False,
        python_deps=["onnx-asr[hub]", "onnxruntime-directml"],
        install_hint="pip install onnx-asr[hub] onnxruntime-directml",
        homepage=f"https://huggingface.co/{_HF_REPO}",
        languages=_MODEL_LANGS,
    )

    def __init__(self) -> None:
        self._model = None
        self._vad = None
        self._loaded_model: Optional[str] = None

    # ---- availability ----
    def is_available(self) -> tuple[bool, str]:
        try:
            import onnx_asr  # noqa: F401
            import onnxruntime  # noqa: F401
            return True, ""
        except ImportError as e:
            return False, f"onnx-asr/onnxruntime не установлен: {e}"

    def install(self, on_log: Optional[Callable[[str], None]] = None) -> bool:
        log_cb = on_log or (lambda m: None)
        log_cb("pip install onnx-asr[hub] onnxruntime-directml …")
        return _pip_install(["onnx-asr[hub]", "onnxruntime-directml"], log_cb)

    # ---- model metadata ----
    def _model_dir(self) -> Path:
        return Path(__file__).resolve().parent.parent / "data" / "models" / "parakeet-onnx"

    def list_models(self) -> list[dict]:
        local = self._model_dir()
        langs_full = [l for l in _MODEL_LANGS if l != "auto"]
        return [{
            "name": _MODEL_NAME,
            "display": "Parakeet TDT 0.6B v3 — 25 языков (вкл. русский), SOTA",
            "size_mb": 640,   # int8 download
            "languages": None,  # multilingual
            "russian": True,
            "desc": ("SOTA 2025-2026, 25 языков (вкл. русский). "
                     "Работает на любом GPU (DirectML) или CPU, без CUDA."),
            "speed": 3,
            "accuracy": 5,
            "langs_full": langs_full,
            "lang_label": "25 языков",
            "downloaded": self.is_model_downloaded(_MODEL_NAME),
            "local_path": str(local),
            "source_url": f"https://huggingface.co/{_HF_REPO}",
        }]

    def is_model_downloaded(self, model: str) -> bool:
        return (self._model_dir() / "encoder-model.int8.onnx").is_file()

    def download_model(
        self,
        model: str,
        on_progress: Optional[Callable[[float, str], None]] = None,
    ) -> Path:
        if model != _MODEL_NAME:
            raise ValueError(f"Unknown model: {model}")
        from huggingface_hub import snapshot_download
        cb = on_progress or (lambda p, m: None)
        dest = self._model_dir()
        dest.mkdir(parents=True, exist_ok=True)
        cb(0, f"Качаю {_HF_REPO} (int8, ~640 МБ) …")
        path = snapshot_download(
            repo_id=_HF_REPO,
            local_dir=dest,
            allow_patterns=_DOWNLOAD_PATTERNS,
        )
        cb(100, f"Готово: {path}")
        return Path(path)

    def check_model_update(self, model: str) -> dict:
        return {
            "provider": self.info.name,
            "model": model,
            "source": f"https://huggingface.co/{_HF_REPO}",
            "has_update": False,
            "local_exists": self.is_model_downloaded(model),
        }

    # ---- inference ----
    def load(self, model: str, device: str = "cpu", **kwargs) -> None:
        avail, why = self.is_available()
        if not avail:
            raise RuntimeError(why)
        if self._loaded_model == model and self._model is not None:
            return  # already loaded
        if not self.is_model_downloaded(model):
            raise FileNotFoundError(
                f"Модель {model} не скачана. Скачайте через UI или "
                f"python -c \"from providers.parakeet_onnx import ParakeetOnnxProvider; "
                f"ParakeetOnnxProvider().download_model('{model}')\""
            )
        import onnx_asr
        import onnxruntime as ort

        # Prefer DirectML (any GPU via DirectX, no CUDA); onnxruntime falls
        # back to CPU automatically when no DML device is available.
        providers = ["DmlExecutionProvider", "CPUExecutionProvider"]
        log.info("Loading %s/%s (quant=%s), providers=%s …",
                 self.info.name, model, _QUANT, ort.get_available_providers())
        self._model = onnx_asr.load_model(
            _ASR_NAME,
            path=str(self._model_dir()),
            quantization=_QUANT,
            providers=providers,
        ).with_vad(onnx_asr.load_vad("silero", providers=providers))
        self._loaded_model = model

    def transcribe(
        self,
        audio_path: Path,
        language: str,
        on_segment: Optional[SegmentCallback] = None,
    ) -> dict:
        if self._model is None:
            raise RuntimeError("Provider not loaded. Call load() first.")

        audio = _load_audio_16k(audio_path)
        duration = len(audio) / _SAMPLE_RATE
        if on_segment:
            on_segment(Segment(start=0.0, end=0.0, text=""), 1)

        try:
            results = self._model.recognize(audio, sample_rate=_SAMPLE_RATE)
        except Exception:
            log.exception("Parakeet ONNX recognize failed")
            raise

        # With VAD the adapter yields segments; accept a list, a tuple, a
        # generator (iterator), or a single result object.
        import collections.abc
        if isinstance(results, (list, tuple)) or isinstance(results, collections.abc.Iterator):
            seg_results = list(results)
        else:
            seg_results = [results]

        segments: list[Segment] = []
        parts: list[str] = []
        for r in seg_results:
            text = (r.text or "").strip()
            start = float(getattr(r, "start", 0.0) or 0.0)
            end = float(getattr(r, "end", 0.0) or 0.0)
            # Fall back to token timestamps if segment bounds are missing.
            if end <= start and getattr(r, "timestamps", None):
                ts = [float(t) for t in r.timestamps if t is not None]
                if ts:
                    start = min(start, ts[0]) if start > 0 else ts[0]
                    end = max(end, ts[-1])
            seg = Segment(start=start, end=end, text=text)
            segments.append(seg)
            if text:
                parts.append(text)
            if on_segment:
                pct = int((end / duration) * 100) if duration else 0
                pct = max(1, min(100, pct))
                on_segment(seg, pct)

        return {
            "text": " ".join(parts).strip(),
            "segments": [s.__dict__ for s in segments],
            "info": {
                "language": language or "auto",
                "duration": float(duration),
                "provider_ep": "directml/cpu",
            },
        }


# ---------- helpers ----------

def _load_audio_16k(path: Path) -> np.ndarray:
    """Decode any audio file to mono 16 kHz float32 PCM in [-1, 1]."""
    import av
    container = av.open(str(path))
    try:
        stream = container.streams.audio[0]
    except IndexError:
        raise RuntimeError("В файле нет аудиодорожки")
    resampler = av.AudioResampler(format="fltp", layout="mono", rate=_SAMPLE_RATE)
    chunks: list[np.ndarray] = []
    for frame in container.decode(stream):
        for f in resampler.resample(frame):
            chunks.append(f.to_ndarray().reshape(-1))
    for f in resampler.resample(None):
        chunks.append(f.to_ndarray().reshape(-1))
    if not chunks:
        raise RuntimeError("Не удалось декодировать аудио")
    return np.concatenate(chunks).astype(np.float32)
