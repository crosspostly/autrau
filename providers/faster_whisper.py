"""Faster-Whisper provider (CTranslate2 backend).

Models live on HuggingFace under `Systran/faster-whisper-{size}`.
This is the default provider — works on CPU and GPU, well-supported.
"""
from __future__ import annotations

import json
import logging
import shutil
import subprocess
import sys
import threading
import urllib.request
from pathlib import Path
from typing import Callable, Optional

from .base import (
    DEFAULT_MODELS_DIR,
    Provider,
    ProviderInfo,
    Segment,
    SegmentCallback,
)

log = logging.getLogger("autrau.faster_whisper")

_HF_API = "https://huggingface.co/api/models"
_MODELS = [
    ("tiny", 75, "75 МБ · самая быстрая, низкая точность"),
    ("base", 142, "142 МБ · для коротких записей"),
    ("small", 466, "466 МБ · баланс скорости и качества"),
    ("medium", 1500, "1.5 ГБ · высокая точность"),
    ("large-v1", 2900, "2.9 ГБ · large v1"),
    ("large-v2", 2900, "2.9 ГБ · large v2"),
    ("large-v3", 2900, "2.9 ГБ · large v3 (рекомендуется)"),
    ("distil-large-v3", 1500, "1.5 ГБ · Distil-Whisper large v3 (быстрее)"),
]
HF_REPO_PREFIX = "Systran/faster-whisper"


class FasterWhisperProvider(Provider):
    info = ProviderInfo(
        name="faster-whisper",
        display_name="Faster-Whisper (CTranslate2)",
        description="Стабильный, точный. CPU и GPU. Рекомендуется по умолчанию.",
        models=[m[0] for m in _MODELS],
        default_model="small",
        requires_gpu=False,
        python_deps=["faster-whisper"],
        install_hint="pip install faster-whisper",
        homepage="https://github.com/SYSTRAN/faster-whisper",
        languages=["ru", "en", "de", "fr", "es", "it", "pt", "zh", "ja",
                   "ko", "tr", "ar", "pl", "uk", "auto"],
    )

    def __init__(self) -> None:
        self._model = None
        self._loaded_model: Optional[str] = None
        self._loaded_device: Optional[str] = None

    # ---- availability ----
    def is_available(self) -> tuple[bool, str]:
        try:
            import faster_whisper  # noqa: F401
            return True, ""
        except ImportError as e:
            return False, f"faster-whisper не установлен: {e}"

    def install(self, on_log: Optional[Callable[[str], None]] = None) -> bool:
        log_cb = on_log or (lambda m: None)
        log_cb("pip install faster-whisper …")
        return _pip_install(["faster-whisper"], log_cb)

    # ---- model metadata ----
    def list_models(self) -> list[dict]:
        out = []
        for name, size_mb, desc in _MODELS:
            local = self.model_local_path(name)
            out.append({
                "name": name,
                "display": f"{name} — {desc}",
                "size_mb": size_mb,
                "downloaded": local.exists(),
                "local_path": str(local),
                "source_url": f"https://huggingface.co/{HF_REPO_PREFIX}-{name}",
            })
        return out

    def model_local_path(self, model: str) -> Path:
        # faster-whisper caches under HF_HOME; for the UI we expose
        # the canonical cache dir but also support a "data/models/" symlink.
        return _hf_cache_dir(f"{HF_REPO_PREFIX}-{model}")

    def is_model_downloaded(self, model: str) -> bool:
        return self.model_local_path(model).exists()

    def check_model_update(self, model: str) -> dict:
        repo = f"{HF_REPO_PREFIX}-{model}"
        local = self.model_local_path(model)
        info: dict = {
            "provider": "faster-whisper",
            "model": model,
            "source": f"https://huggingface.co/{repo}",
            "has_update": False,
            "local_exists": local.exists(),
            "local_sha": _local_sha(local),
        }
        try:
            with urllib.request.urlopen(f"{_HF_API}/{repo}", timeout=10) as r:
                data = json.loads(r.read().decode("utf-8"))
            info["remote_sha"] = data.get("sha", "")
            info["last_modified"] = data.get("lastModified", "")
            if info["local_sha"] and info["remote_sha"] and info["local_sha"] != info["remote_sha"]:
                info["has_update"] = True
        except Exception as e:
            info["error"] = f"Не удалось проверить обновления: {e}"
        return info

    def download_model(
        self,
        model: str,
        on_progress: Optional[Callable[[float, str], None]] = None,
    ) -> Path:
        from huggingface_hub import snapshot_download
        repo = f"{HF_REPO_PREFIX}-{model}"
        cb = on_progress or (lambda p, m: None)
        cb(0, f"Качаю {repo} с huggingface.co …")
        # snapshot_download blocks; progress UI updates via stderr redirect
        # could be added later. For now we tick 0% → 99% → 100%.
        path = snapshot_download(
            repo_id=repo,
            allow_patterns=["*.bin", "*.json", "tokenizer.*", "vocabulary.*"],
        )
        cb(100, f"Готово: {path}")
        return Path(path)

    # ---- inference ----
    def load(self, model: str, device: str = "cpu", **kwargs) -> None:
        avail, why = self.is_available()
        if not avail:
            raise RuntimeError(why)
        if (self._loaded_model == model and self._loaded_device == device
                and self._model is not None):
            return  # already loaded
        from faster_whisper import WhisperModel

        compute_type = kwargs.get("compute_type")
        if compute_type is None:
            compute_type = "float16" if device == "cuda" else "int8"

        log.info("Loading faster-whisper %s on %s (%s)", model, device, compute_type)
        self._model = WhisperModel(
            model, device=device, compute_type=compute_type
        )
        self._loaded_model = model
        self._loaded_device = device

    def transcribe(
        self,
        audio_path: Path,
        language: str,
        on_segment: Optional[SegmentCallback] = None,
    ) -> dict:
        if self._model is None:
            raise RuntimeError("Provider not loaded. Call load() first.")

        kwargs: dict = dict(beam_size=5, vad_filter=True)
        if language and language != "auto":
            kwargs["language"] = language

        segments_iter, info = self._model.transcribe(str(audio_path), **kwargs)

        segments: list[Segment] = []
        full_parts: list[str] = []
        for seg in segments_iter:
            s = Segment(start=seg.start, end=seg.end, text=(seg.text or "").strip())
            if s.text:
                full_parts.append(s.text)
            segments.append(s)
            if on_segment:
                pct = int((seg.end / info.duration) * 100) if info.duration else 0
                pct = max(0, min(100, pct))
                on_segment(s, pct)

        return {
            "text": " ".join(full_parts).strip(),
            "segments": [s.__dict__ for s in segments],
            "info": {
                "language": info.language,
                "language_probability": float(info.language_probability),
                "duration": float(info.duration),
            },
        }


# ---------- helpers ----------

def _hf_cache_dir(repo_id: str) -> Path:
    """Path under HF_HOME where the model would be cached."""
    import os
    base = Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface"))
    return base / "hub" / f"models--{repo_id.replace('/', '--')}"


def _local_sha(path: Path) -> str:
    """Best-effort: hash the refs/main file if present (HF convention)."""
    if not path.exists():
        return ""
    ref = path / "refs" / "main"
    if ref.exists():
        return ref.read_text(encoding="utf-8").strip()
    return ""


def _pip_install(pkgs: list[str], log_cb: Callable[[str], None]) -> bool:
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--upgrade", *pkgs],
            capture_output=True, text=True, timeout=900,
        )
        log_cb(proc.stdout[-500:] if proc.stdout else "")
        if proc.returncode != 0:
            log_cb(f"ERROR: {proc.stderr[-500:]}")
            return False
        return True
    except Exception as e:
        log_cb(f"ERROR: {e}")
        return False
