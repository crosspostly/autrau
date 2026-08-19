"""Transcript export formatters (SRT / VTT / JSON).

Used by `GET /api/transcripts/{name}/export?format=...` to convert saved
segments (sidecar `<name>.segments.json`) into common subtitle / data formats
without re-running the ASR pipeline.

Все форматтеры ожидают список сегментов в формате:
  [{"start": float (sec), "end": float (sec), "text": str}, ...]

Если segments.json отсутствует (например, старая расшифровка без sidecar),
функция `export_text_only()` создаёт «плоский» экспорт — один сегмент,
равный всему тексту. Это лучше, чем 404: пользователь получает файл,
который можно открыть, и явное предупреждение в комментарии.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# ---- time formatters ----

def _fmt_srt_time(seconds: float) -> str:
    """SRT: HH:MM:SS,mmm (comma fractional)."""
    if seconds < 0:
        seconds = 0.0
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int(round((seconds - int(seconds)) * 1000))
    if ms == 1000:
        ms = 0
        s += 1
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _fmt_vtt_time(seconds: float) -> str:
    """WebVTT: HH:MM:SS.mmm (dot fractional)."""
    if seconds < 0:
        seconds = 0.0
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int(round((seconds - int(seconds)) * 1000))
    if ms == 1000:
        ms = 0
        s += 1
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


# ---- formatters ----

def to_srt(segments: list[dict]) -> str:
    """SubRip (.srt) — самый распространённый формат субтитров.

    Пример:
        1
        00:00:00,000 --> 00:00:04,500
        Привет, как дела?

        2
        ...
    """
    out: list[str] = []
    for i, seg in enumerate(segments, start=1):
        start = _fmt_srt_time(float(seg.get("start", 0.0)))
        end = _fmt_srt_time(float(seg.get("end", 0.0)))
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        out.append(f"{i}\n{start} --> {end}\n{text}\n")
    return "\n".join(out).rstrip() + "\n"


def to_vtt(segments: list[dict]) -> str:
    """WebVTT (.vtt) — стандарт W3C для HTML5 video.

    Заголовок WEBVTT обязателен.
    """
    lines: list[str] = ["WEBVTT", ""]
    for seg in segments:
        start = _fmt_vtt_time(float(seg.get("start", 0.0)))
        end = _fmt_vtt_time(float(seg.get("end", 0.0)))
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        lines.append(f"{start} --> {end}")
        lines.append(text)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def to_json_segments(segments: list[dict], meta: dict | None = None) -> str:
    """Полный JSON-экспорт с метаданными и таймстампами.

    Формат:
        {
          "version": 1,
          "language": "ru",
          "provider": "whisper-cpp",
          "model": "large-v3",
          "duration": 8.2,
          "segments": [
            {"start": 0.0, "end": 4.5, "text": "..."},
            ...
          ]
        }
    """
    payload: dict[str, Any] = {
        "version": 1,
        "language": "?",
        "provider": "?",
        "model": "?",
        "duration": 0.0,
        "segments": [
            {
                "start": float(s.get("start", 0.0)),
                "end": float(s.get("end", 0.0)),
                "text": (s.get("text") or "").strip(),
            }
            for s in segments
            if s.get("text")
        ],
    }
    if meta:
        payload.update({k: v for k, v in meta.items() if k != "segments"})
    if payload["segments"]:
        payload["duration"] = max(s["end"] for s in payload["segments"])
    return json.dumps(payload, ensure_ascii=False, indent=2)


def to_plain_text(segments: list[dict], text_fallback: str = "") -> str:
    """Plain text — объединяет segments через пробел, или возвращает fallback
    если segments пустые. Полезно для файлов без segments.json.
    """
    if not segments:
        return text_fallback.strip() + "\n"
    return " ".join((s.get("text") or "").strip() for s in segments if s.get("text")).strip() + "\n"


# ---- segments loader ----

def load_segments(transcript_path: Path) -> list[dict] | None:
    """Загружает segments из sidecar `<stem>.segments.json`.
    Возвращает None если sidecar не существует или повреждён.
    """
    if not transcript_path.is_file():
        return None
    seg_path = transcript_path.with_name(transcript_path.stem + ".segments.json")
    if not seg_path.is_file():
        return None
    try:
        data = json.loads(seg_path.read_text(encoding="utf-8"))
        segs = data.get("segments", [])
        if not isinstance(segs, list):
            return None
        return segs
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return None


def load_meta(transcript_path: Path) -> dict:
    """Загружает meta из sidecar (provider, model, language, duration)."""
    seg_path = transcript_path.with_name(transcript_path.stem + ".segments.json")
    if not seg_path.is_file():
        return {}
    try:
        data = json.loads(seg_path.read_text(encoding="utf-8"))
        return {k: v for k, v in data.items() if k != "segments"}
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return {}


# ---- fallback: text-only (no segments) ----

def export_text_only(transcript_path: Path, text: str) -> str:
    """Когда segments.json отсутствует — генерирует «плоский» SRT с одним
    сегментом. Полезно для старых расшифровок.
    """
    duration = max(1.0, len(text) / 15.0)  # ~15 chars/sec как грубая оценка
    fake = [{"start": 0.0, "end": duration, "text": text.strip()}]
    return to_srt(fake)


# ---- main dispatch ----

SUPPORTED_FORMATS = ("srt", "vtt", "json", "txt")


def export_transcript(
    transcript_path: Path,
    text: str,
    format: str,
) -> tuple[str, str]:
    """Главная точка входа. Возвращает (content, media_type).

    Raises ValueError если формат не поддерживается.
    """
    fmt = format.lower()
    if fmt not in SUPPORTED_FORMATS:
        raise ValueError(f"Неподдерживаемый формат: {format}. "
                         f"Доступные: {', '.join(SUPPORTED_FORMATS)}")

    segments = load_segments(transcript_path)
    meta = load_meta(transcript_path)

    if fmt == "srt":
        if segments:
            return to_srt(segments), "application/x-subrip; charset=utf-8"
        return export_text_only(transcript_path, text), "application/x-subrip; charset=utf-8"
    if fmt == "vtt":
        if segments:
            return to_vtt(segments), "text/vtt; charset=utf-8"
        # Для VTT без segments — тоже плоский, но WEBVTT заголовок уже есть
        return to_vtt([{"start": 0.0,
                        "end": max(1.0, len(text) / 15.0),
                        "text": text.strip()}]), "text/vtt; charset=utf-8"
    if fmt == "json":
        return to_json_segments(segments or [], meta), "application/json; charset=utf-8"
    # txt — простой текст из исходного файла (без # header)
    plain = to_plain_text(segments or [], text)
    return plain, "text/plain; charset=utf-8"
