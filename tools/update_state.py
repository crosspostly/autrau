"""Persistent update state for autrau self-update (v1.5.8).

State в `data/update_state.json`:
    {
      "last_check": "2026-08-20T10:30:00",         # ISO последней проверки
      "current_version": "f843bdb",              # git rev-parse --short HEAD
      "latest_version": "abc1234",               # origin/main commit
      "available": true,                         # есть обновление
      "dismissed_version": "f843bdb",            # юзер нажал "Later" для этой версии
      "last_apply_at": "2026-08-19T18:00:00",    # когда последний раз применяли
      "last_apply_result": "ok",                 # "ok" | "git_failed" | "pip_failed"
      "last_apply_version": "ef13358"            # какая версия была применена
    }

Файл читается при старте (см. server.py lifespan), обновляется после каждой проверки
и после apply. UI читает state и показывает banner если should_notify() == True.

State защищён threading.Lock (RLock) — безопасно вызывать из background thread.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger("autrau.update_state")

# Path resolution: тот же подход что в config.py
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_STATE_PATH = _PROJECT_ROOT / "data" / "update_state.json"

# Lock для thread-safe доступа
_lock = threading.RLock()

# Default state если файла нет
DEFAULT_STATE: dict[str, Any] = {
    "last_check": None,
    "current_version": None,
    "latest_version": None,
    "available": False,
    "dismissed_version": None,
    "last_apply_at": None,
    "last_apply_result": None,
    "last_apply_version": None,
    "check_error": None,  # str: ошибка при последней проверке (если была)
}

_state: dict[str, Any] = dict(DEFAULT_STATE)
_path: Path = DEFAULT_STATE_PATH


def _now_iso() -> str:
    """UTC ISO timestamp для last_check, last_apply_at."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _atomic_write(path: Path, data: dict) -> None:
    """Атомарная запись JSON: write to .tmp → rename. Защита от partial writes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        dir=str(path.parent), prefix=path.name + ".", suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def init(path: Optional[Path] = None) -> None:
    """Загрузить state с диска. Вызвать один раз при старте."""
    global _path, _state
    with _lock:
        _path = Path(path or os.environ.get(
            "AUTRAU_UPDATE_STATE", DEFAULT_STATE_PATH,
        ))
        if _path.exists():
            try:
                data = json.loads(_path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    # Merge with defaults для forward-compat
                    _state = {**DEFAULT_STATE, **data}
                    return
                log.warning("update_state.json не dict, использую defaults")
            except Exception as e:
                log.warning("update_state.json unreadable: %s — using defaults", e)
        _state = dict(DEFAULT_STATE)
        save()


def save() -> None:
    """Сохранить state на диск (atomic write)."""
    with _lock:
        try:
            _atomic_write(_path, _state)
        except Exception as e:
            log.error("Failed to save update state: %s", e)


def get() -> dict[str, Any]:
    """Snapshot текущего state (copy)."""
    with _lock:
        return dict(_state)


def mark_checked(current: str, latest: Optional[str], available: bool, error: Optional[str] = None) -> None:
    """Обновить state после проверки обновлений.

    Args:
        current: текущий commit (HEAD)
        latest: последний commit в origin/main (None если не смогли fetch)
        available: есть ли обновление (latest != current и latest is not None)
        error: текст ошибки (если была, иначе None)
    """
    with _lock:
        _state["last_check"] = _now_iso()
        _state["current_version"] = current
        _state["latest_version"] = latest
        _state["available"] = available
        _state["check_error"] = error
        # Если новая версия появилась, сбрасываем dismissed (юзер должен снова увидеть)
        if available and latest and _state.get("dismissed_version") != latest:
            _state["dismissed_version"] = None
        # Если текущая == latest, точно нет обновления, сбрасываем dismissed
        if current and latest and current == latest:
            _state["available"] = False
            _state["dismissed_version"] = None
    save()


def mark_applied(version: str, result: str) -> None:
    """Обновить state после попытки apply.

    Args:
        version: версия которая была применена (current до apply)
        result: "ok" | "git_failed" | "pip_failed" | "exception"
    """
    with _lock:
        _state["last_apply_at"] = _now_iso()
        _state["last_apply_result"] = result
        _state["last_apply_version"] = version
        # После успешного apply считаем что обновления нет
        if result == "ok":
            _state["available"] = False
            _state["dismissed_version"] = None
    save()


def mark_dismissed(version: str) -> None:
    """Юзер нажал 'Later' для этой версии. Не показывать banner до новой версии."""
    with _lock:
        _state["dismissed_version"] = version
    save()


def should_notify() -> bool:
    """True если UI должен показать banner 'update available'."""
    with _lock:
        if not _state.get("available"):
            return False
        latest = _state.get("latest_version")
        dismissed = _state.get("dismissed_version")
        if not latest:
            return False
        return dismissed != latest


def path() -> Path:
    """Путь к state файлу (для диагностики)."""
    return _path
