"""yt-dlp wrapper: скачать аудио по URL → локальный файл.

Используется `POST /api/yt-dlp` (v1.5.7).

Поддерживает YouTube, Vimeo, Twitter/X, Facebook, Twitch, SoundCloud, Reddit,
и ещё ~1500 сайтов через yt-dlp.

Возвращает:
- info(title, duration, thumbnail) — без скачивания (для preview)
- audio_path — Path к скачанному файлу (wav/m4a/mp3 — лучший доступный)
"""
from __future__ import annotations

import logging
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

log = logging.getLogger("autrau.yt_dlp")


def is_available() -> tuple[bool, str]:
    """Check if yt-dlp is installed in current Python."""
    try:
        import yt_dlp  # noqa: F401
        return True, ""
    except ImportError as e:
        return False, f"yt-dlp не установлен. Поставь: pip install yt-dlp ({e})"


def probe(url: str) -> dict:
    """Get video info without downloading.

    Returns: {title, duration (sec), thumbnail, uploader, webpage_url}
    Raises: RuntimeError if URL is invalid or unreachable.
    """
    ok, why = is_available()
    if not ok:
        raise RuntimeError(why)
    import yt_dlp
    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
        # extract_flat=True — быстрее, но без duration для некоторых
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as e:
        # Strip ANSI color codes from yt-dlp error message
        import re as _re
        msg = str(e)
        msg = _re.sub(r"\x1b\[[0-9;]*m", "", msg)
        raise RuntimeError(f"Не удалось получить информацию: {msg}") from e
    if not info:
        raise RuntimeError("Пустой ответ от yt-dlp")
    return {
        "title": info.get("title", "?"),
        "duration": info.get("duration", 0),
        "thumbnail": info.get("thumbnail", ""),
        "uploader": info.get("uploader") or info.get("channel", "?"),
        "webpage_url": info.get("webpage_url", url),
    }


def download_audio(
    url: str,
    out_dir: Path,
    on_progress: Optional[callable] = None,
) -> Path:
    """Скачать аудио по URL → out_dir/<title>.%(ext)s.

    Returns Path to downloaded audio file.
    Raises: RuntimeError on failure.
    """
    ok, why = is_available()
    if not ok:
        raise RuntimeError(why)
    import yt_dlp

    out_dir.mkdir(parents=True, exist_ok=True)

    # Progress hook для SSE streaming
    def _hook(d: dict) -> None:
        if on_progress is None:
            return
        status = d.get("status", "")
        if status == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            done = d.get("downloaded_bytes", 0)
            pct = int(done * 100 / total) if total else 0
            on_progress(pct, d.get("filename", ""))
        elif status == "finished":
            on_progress(100, d.get("filename", ""))

    opts = {
        "format": "bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio/best",
        "outtmpl": str(out_dir / "%(title).80B.%(ext)s"),
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "wav",
                "preferredquality": "0",  # lossless
            }
        ],
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "progress_hooks": [_hook],
        "concurrent_fragment_downloads": 4,
    }

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            # Postprocessor меняет расширение на .wav (через FFmpegExtractAudio)
            # Найти итоговый файл
            base, _ = ydl.prepare_filename(info).rsplit(".", 1)
            wav_path = out_dir / (Path(base).name + ".wav")
            if wav_path.is_file():
                return wav_path
            # Fallback: ищем любой файл с тем же stem
            for ext in (".wav", ".m4a", ".mp3", ".webm", ".opus"):
                cand = out_dir / (Path(base).name + ext)
                if cand.is_file():
                    return cand
            # Last resort: первый файл в out_dir который появился недавно
            candidates = sorted(
                out_dir.iterdir(),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            if candidates:
                log.warning("Falling back to most recent file: %s", candidates[0])
                return candidates[0]
            raise RuntimeError("Скачано, но файл не найден в " + str(out_dir))
    except Exception as e:
        import re as _re
        msg = _re.sub(r"\x1b\[[0-9;]*m", "", str(e))
        raise RuntimeError(f"Ошибка скачивания: {msg}") from e
    except Exception as e:
        raise RuntimeError(f"Ошибка скачивания: {e}") from e
