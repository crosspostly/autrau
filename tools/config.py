"""Persistent user configuration (JSON file under data/).

Default location: `<project>/data/config.json`. Override with `AUTRAU_CONFIG` env.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Any

log = logging.getLogger("autrau.config")

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = _PROJECT_ROOT / "data" / "config.json"

DEFAULTS: dict[str, Any] = {
    "provider": "faster-whisper",       # active provider name
    "model": "small",                   # active model within that provider
    "device": "cpu",                    # "cpu" or "cuda"
    "language": "ru",
    "beam_size": 5,
    "compute_type": "auto",             # "auto" | "int8" | "float16" | "float32"
    "check_updates_on_start": True,
    "auto_update_app": False,           # self-update on start
    "cleanup_after_days": 0,            # 0 = keep transcripts forever; N>0 = auto-delete older than N days

    # v1.5: Voice memos + hotkey
    "hotkey": "Ctrl+Shift+R",           # global hotkey to start/stop voice recording
    "voice_memo_dir": "data/voice-memos/",  # where to save voice memos
    "voice_memo_cleanup_after_days": 7, # 0 = keep forever; N>0 = auto-delete older than N days
}


_lock = threading.RLock()
_state: dict[str, Any] = {}
_path: Path = DEFAULT_CONFIG_PATH


def init(path: Path | None = None) -> None:
    """Load config from disk (or create defaults). Call once at startup."""
    global _path, _state
    _path = Path(path or os.environ.get("AUTRAU_CONFIG", DEFAULT_CONFIG_PATH))
    _path.parent.mkdir(parents=True, exist_ok=True)
    if _path.exists():
        try:
            data = json.loads(_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                _state = {**DEFAULTS, **data}
            else:
                _state = dict(DEFAULTS)
        except Exception as e:
            log.warning("Config unreadable, using defaults: %s", e)
            _state = dict(DEFAULTS)
    else:
        _state = dict(DEFAULTS)
        save()


def save() -> None:
    with _lock:
        _path.write_text(
            json.dumps(_state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def get(key: str, default: Any = None) -> Any:
    with _lock:
        return _state.get(key, default)


def set(key: str, value: Any) -> None:
    with _lock:
        _state[key] = value
        _path.write_text(
            json.dumps(_state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def all() -> dict[str, Any]:
    with _lock:
        return dict(_state)


def path() -> Path:
    return _path
