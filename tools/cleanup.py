"""Transcript archive + age-based automatic cleanup.

Each successful transcription is saved as a `.txt` file under
`<project>/data/transcripts/` (gitignored). The setting
`cleanup_after_days` (config: `data/config.json`) controls automatic
deletion: files older than N days are removed on a background timer.

Rules:
- `cleanup_after_days <= 0`  → nothing is ever deleted (disabled).
- `cleanup_after_days = N`   → files transcribed N or more days ago are deleted.
"""
from __future__ import annotations

import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger("autrau.cleanup")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TRANSCRIPTS_DIR = PROJECT_ROOT / "data" / "transcripts"

_DAY_SECONDS = 86400


def transcripts_dir() -> Path:
    return TRANSCRIPTS_DIR


def save_transcript(original_name: Optional[str], text: str, info: dict) -> Path:
    """Persist one transcript as a .txt file; returns the path."""
    TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
    stem = Path(original_name or "audio").stem
    safe = "".join(c for c in stem if c.isalnum() or c in " _-").strip() or "audio"
    base = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path = TRANSCRIPTS_DIR / f"{base}_{safe}.txt"
    n = 1
    while path.exists():
        path = TRANSCRIPTS_DIR / f"{base}_{n}_{safe}.txt"
        n += 1
    header = [
        f"# Файл: {original_name or 'неизвестно'}",
        f"# Дата: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"# Модель: {info.get('provider', '?')} / {info.get('model', '?')}",
        f"# Язык: {info.get('language', '?')}",
        "",
    ]
    path.write_text("\n".join(header) + (text or "").strip() + "\n", encoding="utf-8")
    log.info("Saved transcript: %s", path.name)
    return path


def list_files() -> list[Path]:
    if not TRANSCRIPTS_DIR.is_dir():
        return []
    return sorted(f for f in TRANSCRIPTS_DIR.iterdir() if f.is_file())


def count_files() -> int:
    return len(list_files())


def run_cleanup(days: int, dry_run: bool = False) -> dict[str, Any]:
    """Delete transcript files older than `days` days.

    `days <= 0` disables deletion (returns summary without touching files).
    Returns: {ok, enabled, days, deleted, kept, freed_mb}.
    """
    files = list_files()
    if days <= 0 or not files:
        return {
            "ok": True,
            "enabled": days > 0,
            "days": days,
            "deleted": 0,
            "kept": len(files),
            "freed_mb": 0.0,
        }
    cutoff = time.time() - days * _DAY_SECONDS
    deleted = 0
    freed = 0
    kept = 0
    for f in files:
        try:
            age_ok = f.stat().st_mtime < cutoff
        except OSError:
            kept += 1
            continue
        if age_ok:
            if not dry_run:
                try:
                    os.unlink(f)
                except OSError as e:
                    log.warning("Не удалось удалить %s: %s", f.name, e)
                    kept += 1
                    continue
            deleted += 1
            try:
                freed += f.stat().st_size
            except OSError:
                pass
        else:
            kept += 1
    log.info("Cleanup (days=%d): удалено %d, осталось %d", days, deleted, kept)
    return {
        "ok": True,
        "enabled": True,
        "days": days,
        "deleted": deleted,
        "kept": kept,
        "freed_mb": round(freed / 1048576, 2),
    }
