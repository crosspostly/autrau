"""whisper.cpp provider (via `pywhispercpp` Python bindings).

The pywhispercpp wheel bundles prebuilt whisper.cpp binaries, so no cmake
or Visual Studio are required on Windows. CPU-only, very lightweight.

Models are downloaded from `ggerganov/whisper.cpp` on HuggingFace.
"""
from __future__ import annotations

import json
import logging
import urllib.request
from pathlib import Path
from typing import Callable, Optional

from .base import (
    Provider,
    ProviderInfo,
    Segment,
    SegmentCallback,
)
from .faster_whisper import _WHISPER_LANGS, _pip_install

log = logging.getLogger("autrau.whisper_cpp")

_HF_API = "https://huggingface.co/api/models"
_REPO = "ggerganov/whisper.cpp"

# (name, speed 1..5, accuracy 1..5) — 5/1 = быстрее всего / менее точная
_RATINGS = {
    "tiny": (5, 1),
    "base": (4, 2),
    "small": (3, 3),
    "medium": (2, 4),
    "large-v3": (1, 5),
}

# (name, size_mb, description, ggml-file)
#   Мультиязычные модели Whisper (99 языков, incl. ru) — как у faster-whisper.
_MODELS = [
    ("tiny", 75, "Самая быстрая, низкая точность — для черновых проверок", "ggml-tiny.bin"),
    ("base", 142, "Для коротких записей", "ggml-base.bin"),
    ("small", 466, "Баланс скорости и качества", "ggml-small.bin"),
    ("medium", 1500, "Высокая точность", "ggml-medium.bin"),
    ("large-v3", 2900, "Самая точная (рекомендуется), но медленная", "ggml-large-v3.bin"),
]
MODELS_DIR = Path(__file__).resolve().parent.parent / "data" / "models" / "whisper-cpp"
MODELS_DIR.mkdir(parents=True, exist_ok=True)


class WhisperCppProvider(Provider):
    info = ProviderInfo(
        name="whisper-cpp",
        display_name="Whisper.cpp (через pywhispercpp)",
        description="Без PyTorch. Минимум зависимостей. CPU-only, очень быстро.",
        models=[m[0] for m in _MODELS],
        default_model="small",
        requires_gpu=False,
        python_deps=["pywhispercpp"],
        install_hint="pip install pywhispercpp",
        homepage="https://github.com/ggml-org/whisper.cpp",
        languages=["ru", "en", "de", "fr", "es", "it", "pt", "zh", "ja",
                   "ko", "tr", "ar", "pl", "uk", "auto"],
    )

    def __init__(self) -> None:
        self._model = None
        self._loaded_model: Optional[str] = None

    # ---- availability ----
    def is_available(self) -> tuple[bool, str]:
        try:
            import pywhispercpp  # noqa: F401
            return True, ""
        except ImportError as e:
            return False, f"pywhispercpp не установлен: {e}"

    def install(self, on_log: Optional[Callable[[str], None]] = None) -> bool:
        log_cb = on_log or (lambda m: None)
        log_cb("pip install pywhispercpp …")
        return _pip_install(["pywhispercpp"], log_cb)

    # ---- model mgmt ----
    def list_models(self) -> list[dict]:
        out = []
        for name, size_mb, desc, fname in _MODELS:
            local = self.model_local_path(name)
            speed, accuracy = _RATINGS.get(name, (3, 3))
            out.append({
                "name": name,
                "display": f"{name} — {desc}",
                "size_mb": size_mb,
                "languages": None,   # all whisper.cpp models here are multilingual (incl. ru)
                "russian": True,
                "desc": desc,
                "speed": speed,
                "accuracy": accuracy,
                "langs_full": _WHISPER_LANGS,
                "lang_label": "99 языков",
                "downloaded": local.exists(),
                "local_path": str(local),
                "source_url": f"https://huggingface.co/{_REPO}/resolve/main/{fname}",
            })
        return out

    def model_local_path(self, model: str) -> Path:
        return MODELS_DIR / f"ggml-{model}.bin"

    def is_model_downloaded(self, model: str) -> bool:
        return self.model_local_path(model).exists()

    def check_model_update(self, model: str) -> dict:
        info: dict = {
            "provider": "whisper-cpp",
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
        for n, _, _, fname in _MODELS:
            if n == model:
                break
        else:
            raise ValueError(f"Unknown model: {model}")

        url = f"https://huggingface.co/{_REPO}/resolve/main/{fname}"
        dest = self.model_local_path(model)
        cb(0, f"Качаю {url}")
        _download_with_progress(url, dest, cb)
        cb(100, f"Готово: {dest}")
        return dest

    # ---- inference ----
    def load(self, model: str, device: str = "cpu", **kwargs) -> None:
        avail, why = self.is_available()
        if not avail:
            raise RuntimeError(why)
        if not self.is_model_downloaded(model):
            raise FileNotFoundError(
                f"Модель {model} не скачана. Скачайте через UI или "
                f"python -c \"from providers.whisper_cpp import WhisperCppProvider; "
                f"WhisperCppProvider().download_model('{model}')\""
            )
        if self._loaded_model == model and self._model is not None:
            return
        from pywhispercpp.model import Model
        log.info("Loading whisper.cpp %s", model)
        # pywhispercpp v1.5.0+ auto-detects thread count; n_threads removed from API.
        self._model = Model(
            str(self.model_local_path(model)),
            redirect_whispercpp_logs_to=False,
        )
        self._loaded_model = model

    def transcribe(
        self,
        audio_path: Path,
        language: str,
        on_segment: Optional[SegmentCallback] = None,
    ) -> dict:
        if self._model is None:
            raise RuntimeError("Provider not loaded. Call load() first.")
        lang = language if language and language != "auto" else "auto"
        # pywhispercpp returns segments with t0/t1 in centiseconds
        result = self._model.transcribe(
            str(audio_path),
            language=lang,
        )
        segments: list[Segment] = []
        parts: list[str] = []
        # Estimate total duration from last segment.
        last_end = max((getattr(s, "t1", 0) for s in result), default=0) / 100.0
        for s in result:
            text = (s.text or "").strip()
            seg = Segment(start=getattr(s, "t0", 0) / 100.0,
                          end=getattr(s, "t1", 0) / 100.0,
                          text=text)
            segments.append(seg)
            if text:
                parts.append(text)
            if on_segment:
                pct = int((seg.end / last_end) * 100) if last_end else 0
                pct = max(0, min(100, pct))
                on_segment(seg, pct)
        return {
            "text": " ".join(parts).strip(),
            "segments": [s.__dict__ for s in segments],
            "info": {"language": lang, "duration": 0.0},
        }


# ---------- helpers ----------

def _download_with_progress(
    url: str, dest: Path,
    on_progress: Callable[[float, str], None],
    chunk: int = 1024 * 256,
) -> None:
    import time
    req = urllib.request.Request(url, headers={"User-Agent": "autrau/1.0"})
    with urllib.request.urlopen(req, timeout=600) as r, open(dest, "wb") as f:
        total = int(r.headers.get("Content-Length", 0))
        got = 0
        last_pct = -1
        t0 = time.time()
        while True:
            data = r.read(chunk)
            if not data:
                break
            f.write(data)
            got += len(data)
            if total > 0:
                pct = int(got * 100 / total)
                if pct != last_pct:
                    speed = got / max(1e-6, time.time() - t0) / 1024 / 1024
                    on_progress(pct, f"{got/1024/1024:.1f} / {total/1024/1024:.1f} МБ · {speed:.1f} МБ/с")
                    last_pct = pct
