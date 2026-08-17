"""Favorites: star-marked transcripts that are protected from auto-cleanup.

Favorites are stored as a set of transcript filenames in
`<project>/data/favorites.json` (gitignored). `tools.cleanup.run_cleanup()`
skips any file whose name is in the favorites set — even if it matches the
age-based deletion rule. Un-starring a file makes it eligible for deletion
again on the next cleanup run.
"""
from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Optional

log = logging.getLogger("autrau.favorites")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FAVORITES_PATH = PROJECT_ROOT / "data" / "favorites.json"

_lock = threading.RLock()
_cache: Optional[set[str]] = None


def _load_locked() -> set[str]:
    """Load favorites from disk (cached). Caller must hold _lock."""
    global _cache
    if _cache is not None:
        return _cache
    try:
        if FAVORITES_PATH.exists():
            data = json.loads(FAVORITES_PATH.read_text(encoding="utf-8"))
            raw = data if isinstance(data, list) else data.get("favorites", [])
            _cache = {str(n) for n in raw if isinstance(n, str)}
        else:
            _cache = set()
    except Exception as e:
        log.warning("favorites.json unreadable, using empty set: %s", e)
        _cache = set()
    return _cache


def _save_locked(favs: set[str]) -> None:
    FAVORITES_PATH.parent.mkdir(parents=True, exist_ok=True)
    FAVORITES_PATH.write_text(
        json.dumps({"favorites": sorted(favs)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def names() -> set[str]:
    """Return the set of favorited transcript filenames."""
    with _lock:
        return set(_load_locked())


def is_favorite(name: str) -> bool:
    with _lock:
        return name in _load_locked()


def toggle(name: str) -> bool:
    """Flip favorite status for `name`; returns the new state (True = starred)."""
    with _lock:
        favs = _load_locked()
        if name in favs:
            favs.discard(name)
            new_state = False
        else:
            favs.add(name)
            new_state = True
        _save_locked(favs)
        log.info("Favorite %s -> %s", name, new_state)
        return new_state


def set_favorite(name: str, favorite: bool) -> bool:
    """Explicitly set favorite status; returns the new state."""
    with _lock:
        favs = _load_locked()
        if favorite:
            favs.add(name)
        else:
            favs.discard(name)
        _save_locked(favs)
        log.info("Favorite %s -> %s", name, favorite)
        return favorite


def prune(existing: set[str]) -> int:
    """Drop favorites whose file no longer exists. Returns number removed."""
    with _lock:
        favs = _load_locked()
        stale = {n for n in favs if n not in existing}
        if stale:
            for n in stale:
                favs.discard(n)
            _save_locked(favs)
            log.info("Pruned %d stale favorite(s): %s", len(stale), ", ".join(sorted(stale)))
        return len(stale)
