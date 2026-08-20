"""Autrau — local multi-provider audio transcription server.

Endpoints:
  GET  /                          UI
  GET  /health                    quick health probe
  GET  /api/providers             list providers + status + model list
  GET  /api/config                current config
  POST /api/config                update config
  POST /api/cleanup               delete transcripts older than N days (0 = nothing)
  GET  /api/transcripts           list transcripts + favorite flags (prunes dead favorites)
  GET  /api/transcripts/{name}    download/open one transcript .txt file
  DELETE /api/transcripts         delete selected transcripts (body: {"names": [...]})
  POST /api/transcripts/open-folder  open the transcripts folder in the file manager
  GET  /api/voice-memos           list voice memos (from data/voice-memos/)
  GET  /api/voice-memos/{name}    download/open one voice memo .txt file
  DELETE /api/voice-memos         delete selected voice memos (body: {"names": [...]})
  POST /api/voice-memos/open-folder  open the voice-memos folder
  POST /api/voice/start           start a voice-memo recording session (returns {id})
  POST /api/voice/chunk           append audio chunk to active session (multipart audio/webm)
  POST /api/voice/stop            finalize session → transcribe → save to voice-memos/
  POST /api/favorites             toggle/set favorite (favorites survive cleanup)
  GET  /api/updates               check app + model updates (?stream=1 — SSE progress)
  POST /api/updates/app           run self-update (git pull + pip upgrade)
  POST /api/model/download        download a model for a provider (SSE progress)
  GET  /api/model/check           check update for one model
  POST /api/provider/load         (re)load provider+model into memory
  POST /transcribe                main endpoint, streams SSE progress

Env:  AUTRAU_PORT, AUTRAU_HOST (defaults 8000, 127.0.0.1)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

from fastapi import FastAPI, File, Form, HTTPException, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

# Add project root to path so `providers` and `tools` resolve when started directly
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from providers import registry  # noqa: E402
from providers.base import Segment  # noqa: E402
import tools.config as cfg  # noqa: E402
import tools.check as check  # noqa: E402
import tools.update as upd  # noqa: E402
import tools.cleanup as clean  # noqa: E402
import tools.favorites as fav  # noqa: E402
import tools.translation as tr  # noqa: E402
import tools.yt_dlp as ytdlp  # noqa: E402
import tools.system_audio as sysaudio  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    force=True,  # перезаписать дефолтный uvicorn-хендлер, чтобы все наши логи шли в stdout
)
# Дублируем app-логи в файл autrau-server.out.log (чтобы можно было посмотреть после)
try:
    _file_handler = logging.FileHandler(
        PROJECT_ROOT / "autrau-server.out.log", encoding="utf-8", mode="a"
    )
    _file_handler.setLevel(logging.INFO)
    _file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    logging.getLogger("autrau").addHandler(_file_handler)
except Exception:
    pass
# uvicorn access-логи не дублируем
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
log = logging.getLogger("autrau.server")

HOST = os.environ.get("AUTRAU_HOST", "127.0.0.1")
PORT = int(os.environ.get("AUTRAU_PORT", "8000"))
MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "500"))

# Video containers (и audio-only .m4a) — перед распознаванием извлекается аудиодорожка (ffmpeg).
# .m4a = aac в mp4-контейнере; onnx-asr не всегда декодирует его нативно.
VIDEO_EXTS = {
    ".mp4", ".m4v", ".mkv", ".mov", ".avi", ".webm",
    ".flv", ".wmv", ".mpg", ".mpeg", ".ts", ".mts", ".3gp",
    ".m4a",  # audio-only, aac — пропускаем через ffmpeg для надёжности
}

# ---- App ----

# In-memory loaded model state — must be declared before lifespan() so
# the handler can assign _loaded_lock at startup.
_loaded_lock: Optional[asyncio.Lock] = None
_loaded_provider: Optional[str] = None
_loaded_model: Optional[str] = None
_loaded_device: Optional[str] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Modern lifespan handler (replaces deprecated on_event)."""
    global _loaded_lock
    _loaded_lock = asyncio.Lock()
    cfg.init()
    # v1.5.8: persistent update state
    _ustate.init()
    if cfg.get("check_updates_on_start"):
        log.info("Startup update check (background) …")
        asyncio.create_task(_startup_check())
    # v1.5.8: periodic update check (если auto_update_app или просто показать баннер)
    asyncio.create_task(_update_scheduler())
    asyncio.create_task(_cleanup_loop())
    # v1.5: проверка translation providers (с таймаутом, чтобы не зависнуть)
    asyncio.create_task(_translation_startup_check())
    yield
    # Shutdown: nothing to clean up — provider instances hold their own resources.


async def _startup_check() -> None:
    try:
        report = upd.check_all_updates()
        if report.get("app", {}).get("has_update"):
            log.warning("App update available. Run update.bat or call /api/updates/app")
    except Exception as e:
        log.warning("Startup check failed: %s", e)
    # v1.5.8: persist state
    try:
        from tools.update import current_version, latest_version
        current = current_version()
        latest = latest_version()
        available = (latest is not None and current != "unknown" and current != latest)
        _ustate.mark_checked(current, latest, available=available)
    except Exception as e:
        log.warning("Failed to update state: %s", e)


async def _update_scheduler() -> None:
    """Periodic background check (каждые update_check_interval_hours)."""
    # First check через 30s (дать серверу прогреться)
    await asyncio.sleep(30)
    while True:
        try:
            interval_h = float(cfg.get("update_check_interval_hours", 6))
            interval_s = max(60, int(interval_h * 3600))  # минимум 1 минута
            log.debug("Update scheduler: next check in %ds (interval=%.1fh)",
                      interval_s, interval_h)
            await asyncio.sleep(interval_s)
            # Check
            from tools.update import current_version, latest_version
            current = current_version()
            latest = latest_version()
            available = (latest is not None and current != "unknown" and current != latest)
            _ustate.mark_checked(current, latest, available=available)
            log.info("Periodic update check: current=%s latest=%s available=%s",
                     current, latest, available)
            # Auto-apply
            if available and bool(cfg.get("auto_update_app", False)):
                log.info("auto_update_app=true, applying update…")
                from tools.update import app_pull, deps_upgrade
                try:
                    pull = app_pull()
                    if pull.get("ok"):
                        deps = deps_upgrade()
                        if deps.get("ok"):
                            _ustate.mark_applied(current, "ok")
                            log.info("Update applied, restarting in 2s …")
                            await asyncio.sleep(2)
                            _os.execv(sys.executable, [sys.executable] + sys.argv)
                        else:
                            _ustate.mark_applied(current, "pip_failed")
                            log.error("Auto-update pip failed: %s", deps.get("detail"))
                    else:
                        _ustate.mark_applied(current, "git_failed")
                        log.error("Auto-update git pull failed: %s", pull.get("detail"))
                except Exception as e:
                    _ustate.mark_applied(current, "exception")
                    log.exception("Auto-update failed: %s", e)
        except asyncio.CancelledError:
            break
        except Exception as e:
            log.warning("Update scheduler error: %s (retry in 5 min)", e)
            await asyncio.sleep(300)


async def _translation_startup_check() -> None:
    """Проверяет доступность translation providers при старте (с таймаутом).
    Если argos не установлен или моделей нет — автоматически запускает установку в фоне.
    """
    import asyncio as _aio
    log.info("─" * 60)
    log.info("🌐 TRANSLATION PROVIDERS")
    log.info("─" * 60)
    needs_argos_install = False
    for name in ("minimax", "libretranslate", "argos"):
        try:
            prov = tr.get_provider(
                name,
                libretranslate_url=cfg.get("libretranslate_url", ""),
                libretranslate_key=cfg.get("libretranslate_key", ""),
                minimax_key=cfg.get("minimax_key", ""),
            )
            if prov is None:
                if name == "minimax":
                    log.info(f"  ✗ {name:14}  не задан api_key (положите в ~/.minimax/auth.json или config)")
                else:
                    log.info(f"  ✗ {name:14}  не сконфигурирован")
                continue
            # Проверяем в отдельном потоке с таймаутом (is_available может зависнуть)
            avail_result = [None, None]
            def _check():
                try:
                    avail, why = prov.is_available()
                    avail_result[0] = avail
                    avail_result[1] = why
                except Exception as e:
                    avail_result[0] = False
                    avail_result[1] = f"exception: {e}"
            t = threading.Thread(target=_check, daemon=True)
            t.start()
            # Ждём до 5 секунд через asyncio.sleep
            for _ in range(50):
                if not t.is_alive():
                    break
                await _aio.sleep(0.1)
            if t.is_alive():
                log.info(f"  ⏱ {name:14}  таймаут 5с (is_available завис)")
            else:
                avail, why = avail_result
                if avail:
                    log.info(f"  ✓ {name:14}  OK")
                else:
                    log.info(f"  ✗ {name:14}  {why or 'недоступен'}")
                    # Если argos не работает (нет пакета или нет моделей) — поставим автоматически
                    if name == "argos" and (
                        "pip install" in (why or "")
                        or "модели отсутствуют" in (why or "")
                    ):
                        needs_argos_install = True
        except Exception as e:
            log.info(f"  ✗ {name:14}  {e}")
    log.info("─" * 60)
    if cfg.get("translate_to_en"):
        log.info("translate_to_en = ON — перевод будет пытаться работать")
    else:
        log.info("translate_to_en = OFF — перевод выключен (поставь галочку в UI для включения)")

    # Авто-установка Argos в фоне, если он не работает
    if needs_argos_install:
        log.info("🔧 Argos не работает → авто-установка в фоне (pip + модели, ~336 МБ)")
        log.info("   Следи за /api/translate/providers — когда станет OK, всё готово")
        threading.Thread(target=_bg_install_argos, daemon=True).start()


def _bg_install_argos() -> None:
    """Фоновая авто-установка Argos при старте: pip + обе модели en↔ru."""
    import subprocess as _sp
    # 1. pip install (если не стоит)
    try:
        import argostranslate  # noqa: F401
        log.info("  argostranslate: уже установлен")
    except ImportError:
        log.info("  pip install argostranslate langdetect …")
        try:
            proc = _sp.run(
                [sys.executable, "-m", "pip", "install", "--quiet", "argostranslate", "langdetect"],
                capture_output=True, text=True, timeout=300,
            )
            if proc.returncode != 0:
                log.error("  pip install FAILED: %s", proc.stderr[-300:])
                return
            log.info("  argostranslate + langdetect: установлены")
        except Exception as e:
            log.error("  pip install exception: %s", e)
            return

    # 2. Скачиваем модели en_ru + ru_en в фоне
    try:
        from argostranslate import package as _pkg
        log.info("  Обновляю индекс пакетов …")
        _pkg.update_package_index()
        available = {(p.from_code, p.to_code): p for p in _pkg.get_available_packages()}
        installed = {(p.from_code, p.to_code) for p in _pkg.get_installed_packages()}
        for pair, label in [(("en", "ru"), "en→ru (187 МБ)"), (("ru", "en"), "ru→en (149 МБ)")]:
            if pair in installed:
                log.info("  модель %s: уже установлена", label)
                continue
            if pair not in available:
                log.error("  модель %s: НЕТ в индексе пакетов", label)
                continue
            log.info("  скачиваю %s с argos-net.com …", label)
            try:
                available[pair].install()
                log.info("  модель %s: ГОТОВА ✓", label)
            except Exception as e:
                log.error("  модель %s: ошибка скачивания: %s", label, e)
        log.info("  Argos авто-установка: завершена")
    except Exception as e:
        log.error("  Argos авто-установка: %s", e)


_CLEANUP_INTERVAL_S = 6 * 3600  # run age-based cleanup every 6 hours


async def _cleanup_loop() -> None:
    """Periodically delete transcripts older than `cleanup_after_days` (0 = off)."""
    while True:
        try:
            days = int(cfg.get("cleanup_after_days", 0))
            if days > 0:
                clean.run_cleanup(days)
        except Exception as e:
            log.warning("Cleanup failed: %s", e)
        await asyncio.sleep(_CLEANUP_INTERVAL_S)


app = FastAPI(title="Autrau", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
STATIC_DIR = PROJECT_ROOT
app.mount("/static", StaticFiles(directory=str(STATIC_DIR / "static")), name="static")


# ---- HTML ----
@app.get("/", response_class=HTMLResponse)
async def root() -> HTMLResponse:
    return HTMLResponse((STATIC_DIR / "index.html").read_text(encoding="utf-8"))


# ---- Health ----
@app.get("/health")
async def health() -> dict:
    py = check._check_python()
    return {
        "status": "ok",
        "version": app.version,
        "python_ok": py["ok"],
        "loaded": {
            "provider": _loaded_provider,
            "model": _loaded_model,
            "device": _loaded_device,
        },
    }


# ---- Config ----
@app.get("/api/config")
async def api_get_config() -> dict:
    return cfg.all()


@app.post("/api/config")
async def api_set_config(payload: dict) -> dict:
    for k, v in payload.items():
        if k in cfg.DEFAULTS:
            cfg.set(k, v)
    return cfg.all()


# ---- Cleanup ----
@app.post("/api/cleanup")
async def api_cleanup(payload: Optional[dict] = None) -> dict:
    """Delete transcripts older than N days immediately. Returns summary.

    Body optional: {"days": N} overrides the configured value for this run;
    default uses cfg.cleanup_after_days (0 = nothing deleted).
    """
    days = (payload or {}).get("days")
    if days is None:
        days = cfg.get("cleanup_after_days", 0)
    try:
        days = int(days)
    except (TypeError, ValueError):
        raise HTTPException(400, "days должен быть целым числом")
    report = clean.run_cleanup(days)
    report["active"] = int(cfg.get("cleanup_after_days", 0)) > 0
    return report


def _open_in_file_manager(path: Path) -> None:
    """Open a folder in the OS file manager (best-effort, non-blocking)."""
    path = Path(path)
    if sys.platform == "win32":
        os.startfile(str(path))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


def _probe_duration(video_path: Path) -> float | None:
    """Длительность медиа в секундах через ffprobe. None, если ffprobe недоступен."""
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return None
    try:
        proc = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)],
            capture_output=True, text=True, timeout=10,
        )
        if proc.returncode != 0 or not proc.stdout.strip():
            return None
        return float(proc.stdout.strip())
    except (ValueError, subprocess.TimeoutExpired, OSError):
        return None


def _extract_audio(video_path: Path,
                   on_progress: "Callable[[int, str], None] | None" = None
                   ) -> Path:
    """Извлечь аудиодорожку из видео в 16 кГц моно WAV (через ffmpeg).

    Если передан on_progress(percent, text) — вызывается по ходу извлечения.
    percent считается от total секунд (полученных через ffprobe); если
    длительность неизвестна — шлём 0% старт, без промежуточных обновлений.
    """
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError(
            "для видео нужен ffmpeg — установите его и перезапустите приложение"
        )
    out = Path(f"{video_path}.wav")
    total = _probe_duration(video_path)
    cmd = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
           "-progress", "pipe:1",
           "-i", str(video_path), "-vn", "-ac", "1", "-ar", "16000", str(out)]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, bufsize=1)
    last_pct = -1
    last_emit = 0.0
    try:
        if on_progress is not None and total and total > 0:
            on_progress(0, "🎬 извлекаю звук из видео … 0%")
        for raw in proc.stdout:
            line = raw.strip()
            if not line.startswith("out_time_us="):
                continue
            if total is None or total <= 0:
                continue
            try:
                us = int(line.split("=", 1)[1])
            except ValueError:
                continue
            pct = min(99, max(0, int(us / 1_000_000 / total * 100)))
            now = time.monotonic()
            if pct != last_pct and (now - last_emit) >= 0.25:
                last_pct = pct
                last_emit = now
                if on_progress is not None:
                    on_progress(pct, f"🎬 извлекаю звук из видео … {pct}%")
        rc = proc.wait(timeout=600)
    finally:
        if proc.stdout:
            proc.stdout.close()
        if proc.stderr:
            proc.stderr.close()
    if rc != 0 or not out.is_file():
        stderr = b""
        try:
            stderr = proc.stderr.read().encode("utf-8", errors="replace") if proc.stderr else b""
        except Exception:
            pass
        raise RuntimeError(
            f"не удалось извлечь звук из видео (ffmpeg rc={rc}): "
            f"{stderr[-300:].decode('utf-8', errors='replace')}"
        )
    if on_progress is not None:
        on_progress(100, "🎬 извлекаю звук из видео … 100%")
    return out


# ---- Transcripts & favorites ----
@app.get("/api/transcripts")
async def api_transcripts() -> dict:
    """List saved transcripts with favorite flags.

    Stale favorite entries (files that no longer exist) are pruned from
    `data/favorites.json` so the list never shows dead records.
    """
    items = clean.list_transcripts()
    existing = {it["name"] for it in items}
    fav.prune(existing)
    favorites = fav.names()
    for it in items:
        it["is_favorite"] = it["name"] in favorites
    return {"transcripts": items, "count": len(items), "dir": str(clean.transcripts_dir())}


@app.delete("/api/transcripts")
async def api_transcripts_delete(payload: dict) -> dict:
    """Delete selected transcript files.

    Body: {"names": ["file1.txt", ...]}. Names are sanitized with `Path.name`
    so path traversal is impossible. Deleted files are also removed from the
    favorites list.
    """
    names = payload.get("names")
    if not isinstance(names, list) or not names:
        raise HTTPException(400, "names обязателен (массив имён файлов)")
    deleted: list[str] = []
    missing: list[str] = []
    for raw in names:
        if not isinstance(raw, str) or not raw:
            continue
        name = Path(raw).name
        path = clean.transcripts_dir().joinpath(name)
        if not path.is_file():
            missing.append(name)
            continue
        try:
            os.unlink(path)
            deleted.append(name)
        except OSError as e:
            raise HTTPException(500, f"Не удалось удалить '{name}': {e}")
    if deleted:
        fav.prune({f.name for f in clean.list_files()})
    return {"ok": True, "deleted": deleted, "missing": missing}


@app.post("/api/transcripts/open-folder")
async def api_transcripts_open_folder() -> dict:
    """Open the transcripts folder in the system file manager (local app)."""
    d = clean.transcripts_dir()
    d.mkdir(parents=True, exist_ok=True)
    try:
        _open_in_file_manager(d)
    except Exception as e:
        raise HTTPException(500, f"Не удалось открыть папку: {e}")
    return {"ok": True, "dir": str(d)}


@app.get("/api/transcripts/{name}")
async def api_transcript_file(name: str) -> Any:
    """Serve one saved transcript .txt file.

    The name is sanitized via `Path.name` to prevent path traversal, then
    resolved inside `data/transcripts/`.
    """
    safe = Path(name).name
    path = clean.transcripts_dir().joinpath(safe)
    if not path.is_file():
        raise HTTPException(404, f"Расшифровка '{name}' не найдена")
    return FileResponse(
        path,
        media_type="text/plain; charset=utf-8",
        filename=safe,
        content_disposition_type="inline",  # открыть в новой вкладке, а не «сохранить файл»
    )


@app.get("/api/transcripts/{name}/export")
async def api_transcript_export(name: str, format: str = "srt") -> Any:
    """Экспорт расшифровки в SRT / VTT / JSON / TXT (v1.5.6).

    Использует sidecar `<stem>.segments.json` если есть, иначе — «плоский»
    экспорт из одного сегмента (равного всему тексту). Так старые расшифровки
    без таймстампов тоже можно скачать, хоть и без точного времени.

    Query: `format=srt|vtt|json|txt` (default `srt`).
    Response: файл с правильным Content-Disposition: attachment (скачивание).
    """
    from tools import exports as exp
    safe = Path(name).name
    path = clean.transcripts_dir().joinpath(safe)
    if not path.is_file():
        raise HTTPException(404, f"Расшифровка '{name}' не найдена")

    fmt = (format or "srt").lower()
    if fmt not in exp.SUPPORTED_FORMATS:
        raise HTTPException(400, f"Неподдерживаемый формат: {format}. "
                                 f"Доступные: {', '.join(exp.SUPPORTED_FORMATS)}")

    # Текст нужен для fallback и txt формата
    raw = path.read_text(encoding="utf-8")
    # Убираем # заголовок
    text_lines = [ln for ln in raw.splitlines() if not ln.startswith("#")]
    text_only = "\n".join(text_lines).strip()

    try:
        content, media_type = exp.export_transcript(path, text_only, fmt)
    except Exception as e:
        log.exception("Export failed for %s: %s", safe, e)
        raise HTTPException(500, f"Ошибка экспорта: {e}")

    # Имя файла: 2026-08-19_test_ru.mp3.srt
    out_name = path.stem + f".{fmt}"
    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{out_name}"',
            "Cache-Control": "no-store",
        },
    )


# ---- yt-dlp: download audio from URL → transcribe (v1.5.7) ----

@app.get("/api/yt-dlp/info")
async def api_yt_dlp_info(url: str) -> dict:
    """Get video metadata (title, duration, thumbnail) without downloading.

    Query: `?url=<video_url>`
    Returns: `{title, duration, thumbnail, uploader, webpage_url}`
    """
    if not url or not url.strip():
        raise HTTPException(400, "url обязателен")
    ok, why = ytdlp.is_available()
    if not ok:
        raise HTTPException(412, why)
    try:
        return ytdlp.probe(url.strip())
    except RuntimeError as e:
        raise HTTPException(400, str(e))


@app.post("/api/yt-dlp")
async def api_yt_dlp(payload: dict) -> Any:
    """Download audio from URL → transcribe (SSE stream with progress).

    Body: {url, language?, provider?, model?, device?, format?}
    SSE events:
      - {type: "info", payload: {title, duration}}
      - {type: "downloading", percent: int}
      - {type: "transcribing", percent: int}
      - {type: "done", payload: {text, file, segments, translation, ...}}
      - {type: "error", payload: "..."}
    """
    from tools import yt_dlp as _ytdlp  # avoid shadowing
    url = (payload.get("url") or "").strip()
    if not url:
        raise HTTPException(400, "url обязателен")
    language = payload.get("language") or cfg.get("language", "ru")
    p_name = payload.get("provider") or cfg.get("provider")
    m_name = payload.get("model") or cfg.get("model")
    dev = payload.get("device") or cfg.get("device", "cpu")
    fmt = (payload.get("format") or "txt").lower()

    ok, why = _ytdlp.is_available()
    if not ok:
        raise HTTPException(412, why)

    # Validate provider/model
    try:
        p = registry.get(p_name)
    except KeyError:
        raise HTTPException(404, f"Провайдер '{p_name}' не найден")
    if not p.is_available()[0]:
        raise HTTPException(412, p.is_available()[1] or "Провайдер недоступен")

    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_event_loop()

    def _enqueue(kind: str, percent: int, payload: Any) -> None:
        try:
            loop.call_soon_threadsafe(queue.put_nowait, (kind, percent, payload))
        except RuntimeError:
            pass

    def producer() -> None:
        tmp_dir = Path(tempfile.gettempdir()) / f"autrau-yt-{int(time.time())}"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        try:
            # 1. Probe
            _enqueue("info", 0, _ytdlp.probe(url))
            # 2. Download
            _enqueue("downloading", 0, {"url": url})
            audio_path = _ytdlp.download_audio(
                url, tmp_dir,
                on_progress=lambda pct, fn: _enqueue("downloading", pct, {"file": fn}),
            )
            # 3. Transcribe (reuse main provider pipeline)
            _enqueue("transcribing", 0, {"file": str(audio_path)})

            def on_seg(seg: Segment, percent: int) -> None:
                _enqueue("transcribing", percent, seg.__dict__)
            out = p.transcribe(audio_path, language, on_segment=on_seg)
            try:
                _info = out.get("info", {}) or {}
                _info.setdefault("provider", p_name)
                _info.setdefault("model", m_name)
                _info["source_url"] = url
                _path = clean.save_transcript(
                    audio_path.name, out.get("text", ""), _info,
                    segments=out.get("segments") or [],
                )
                if _path:
                    tpath = _maybe_translate(out.get("text", ""), _info, target_path=_path)
                    if tpath and tpath.is_file():
                        try:
                            raw = tpath.read_text(encoding="utf-8")
                            lines = [ln for ln in raw.splitlines() if not ln.startswith("#")]
                            out["translation"] = "\n".join(lines).strip()
                            out["translation_provider"] = _info.get("translation_provider", "argos")
                        except Exception:
                            pass
                    if _path:
                        out["file"] = _path.name
            except Exception as se:
                log.warning("Не удалось сохранить yt-dlp транскрипт: %s", se)
            _enqueue("done", 100, out)
        except Exception as e:
            log.exception("yt-dlp flow failed")
            _enqueue("error", 0, f"{type(e).__name__}: {e}")
        finally:
            # Cleanup temp dir
            try:
                shutil.rmtree(tmp_dir, ignore_errors=True)
            except Exception:
                pass

    loop.run_in_executor(None, producer)

    async def stream():
        try:
            while True:
                kind, percent, payload = await queue.get()
                evt = json.dumps({"type": kind, "percent": percent, "payload": payload},
                                 ensure_ascii=False)
                yield f"data: {evt}\n\n"
                if kind in ("done", "error"):
                    break
        except asyncio.CancelledError:
            log.info("yt-dlp client disconnected")
            raise

    return StreamingResponse(
        stream(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no",
                 "Connection": "keep-alive"},
    )


# ---- System audio loopback (v1.5.7) ----

# Single instance: только одна запись в один момент
_sysaudio_recorder: Optional[sysaudio.SystemAudioRecorder] = None
_sysaudio_lock = threading.Lock()


@app.get("/api/system-audio/devices")
async def api_system_audio_devices() -> dict:
    """List available loopback devices (что можно захватить из колонок)."""
    ok, why = sysaudio.is_available()
    if not ok:
        return {"available": False, "reason": why, "devices": []}
    return {
        "available": True,
        "devices": sysaudio.list_loopback_devices(),
    }


@app.post("/api/system-audio/start")
async def api_system_audio_start(payload: dict) -> dict:
    """Start recording from a loopback device.

    Body: {device_id: int (default 0)}
    Returns: {started: true, device: "..."}
    """
    global _sysaudio_recorder
    ok, why = sysaudio.is_available()
    if not ok:
        raise HTTPException(412, why)
    device_id = int(payload.get("device_id") or 0)
    with _sysaudio_lock:
        if _sysaudio_recorder is not None:
            raise HTTPException(409, "Recording already in progress. Stop first.")
        try:
            rec = sysaudio.SystemAudioRecorder(device_id=device_id)
            rec.start()
            _sysaudio_recorder = rec
        except Exception as e:
            raise HTTPException(500, f"Failed to start: {e}")
    # wait a tiny bit to confirm thread is alive
    time.sleep(0.1)
    elapsed = _sysaudio_recorder.elapsed_sec() if _sysaudio_recorder else 0
    if elapsed < 0.05:
        # Thread died immediately
        with _sysaudio_lock:
            _sysaudio_recorder = None
        raise HTTPException(500, "Recording thread died immediately. Проверьте что loopback-устройство доступно.")
    devices = sysaudio.list_loopback_devices()
    device_name = devices[device_id]["name"] if device_id < len(devices) else "?"
    return {
        "started": True,
        "device": device_name,
        "elapsed_sec": round(elapsed, 2),
    }


@app.post("/api/system-audio/stop")
async def api_system_audio_stop(payload: dict) -> Any:
    """Stop recording → transcribe → return SSE stream with progress.

    Body: {language?, provider?, model?, device?, save_to?: "transcripts"|"voice-memos"}
    SSE events: progress (transcribing) → done (with text/segments/translation) | error
    """
    global _sysaudio_recorder
    with _sysaudio_lock:
        rec = _sysaudio_recorder
    if rec is None:
        raise HTTPException(409, "No recording in progress")
    wav_path = rec.stop()
    with _sysaudio_lock:
        _sysaudio_recorder = None
    if wav_path is None or not wav_path.exists():
        raise HTTPException(500, "Recording failed (no WAV produced)")

    language = payload.get("language") or cfg.get("language", "ru")
    p_name = payload.get("provider") or cfg.get("provider")
    m_name = payload.get("model") or cfg.get("model")
    dev = payload.get("device") or cfg.get("device", "cpu")
    save_to = (payload.get("save_to") or "voice-memos").lower()

    try:
        p = registry.get(p_name)
    except KeyError:
        raise HTTPException(404, f"Провайдер '{p_name}' не найден")
    if not p.is_available()[0]:
        raise HTTPException(412, p.is_available()[1] or "Провайдер недоступен")

    # Lazy-load если ещё не загружен
    global _loaded_provider, _loaded_model, _loaded_device
    if not (_loaded_provider == p_name and _loaded_model == m_name and _loaded_device == dev):
        if not p.is_model_downloaded(m_name):
            raise HTTPException(404, f"Модель {m_name} не скачана")
        log.info("Lazy-loading %s/%s on %s …", p_name, m_name, dev)
        loop0 = asyncio.get_event_loop()
        await loop0.run_in_executor(None, lambda: p.load(m_name, device=dev))
        _loaded_provider, _loaded_model, _loaded_device = p_name, m_name, dev

    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_event_loop()

    def _enqueue(kind: str, percent: int, payload: Any) -> None:
        try:
            loop.call_soon_threadsafe(queue.put_nowait, (kind, percent, payload))
        except RuntimeError:
            pass

    def producer() -> None:
        try:
            _enqueue("info", 0, {"file": str(wav_path), "elapsed_sec": rec.elapsed_sec()})
            out = p.transcribe(wav_path, language)
            try:
                _info = out.get("info", {}) or {}
                _info.setdefault("provider", p_name)
                _info.setdefault("model", m_name)
                _info["source"] = "system-audio"
                if save_to == "transcripts":
                    _path = clean.save_transcript(
                        "system_audio.wav", out.get("text", ""), _info,
                        segments=out.get("segments") or [],
                    )
                else:
                    _path = clean.save_voice_memo(
                        out.get("text", ""), _info,
                        segments=out.get("segments") or [],
                    )
                if _path:
                    tpath = _maybe_translate(out.get("text", ""), _info, target_path=_path)
                    if tpath and tpath.is_file():
                        try:
                            raw = tpath.read_text(encoding="utf-8")
                            lines = [ln for ln in raw.splitlines() if not ln.startswith("#")]
                            out["translation"] = "\n".join(lines).strip()
                            out["translation_provider"] = _info.get("translation_provider", "argos")
                        except Exception:
                            pass
                    if _path:
                        out["file"] = _path.name
            except Exception as se:
                log.warning("Не удалось сохранить system-audio транскрипт: %s", se)
            _enqueue("done", 100, out)
        except Exception as e:
            log.exception("system-audio transcribe failed")
            _enqueue("error", 0, f"{type(e).__name__}: {e}")
        finally:
            try:
                wav_path.unlink()
            except OSError:
                pass

    loop.run_in_executor(None, producer)

    async def stream():
        try:
            while True:
                kind, percent, payload = await queue.get()
                evt = json.dumps({"type": kind, "percent": percent, "payload": payload},
                                 ensure_ascii=False)
                yield f"data: {evt}\n\n"
                if kind in ("done", "error"):
                    break
        except asyncio.CancelledError:
            log.info("system-audio client disconnected")
            raise

    return StreamingResponse(
        stream(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no",
                 "Connection": "keep-alive"},
    )


@app.post("/api/favorites")
async def api_favorites(payload: dict) -> dict:
    """Toggle or explicitly set favorite status for one transcript.

    Body: {"name": "file.txt"}            — toggle current state;
          {"name": "file.txt", "favorite": true|false} — explicit set.
    Favorites are protected from auto-cleanup (see tools.cleanup.run_cleanup);
    un-starring makes the file eligible again on the next cleanup run.
    Returns 404 when the transcript file does not exist.
    """
    name = payload.get("name")
    if not name or not isinstance(name, str):
        raise HTTPException(400, "name обязателен")
    if not clean.transcripts_dir().joinpath(name).is_file():
        raise HTTPException(404, f"Расшифровка '{name}' не найдена")
    if "favorite" in payload:
        state = fav.set_favorite(name, bool(payload["favorite"]))
    else:
        state = fav.toggle(name)
    return {"name": name, "is_favorite": state}


# ---- Voice memos (v1.5) ----
@app.get("/api/voice-memos")
async def api_voice_memos() -> dict:
    """List voice memos from data/voice-memos/."""
    items = clean.list_voice_memos()
    return {"voice_memos": items, "count": len(items), "dir": str(clean.voice_memos_dir())}


@app.get("/api/voice-memos/{name}")
async def api_voice_memo_file(name: str) -> Any:
    """Serve one voice memo .txt file."""
    safe = Path(name).name
    path = clean.voice_memos_dir().joinpath(safe)
    if not path.is_file():
        raise HTTPException(404, f"Голосовая заметка '{name}' не найдена")
    return FileResponse(
        path, media_type="text/plain; charset=utf-8",
        filename=safe,
        content_disposition_type="inline",  # открыть в браузере, не «сохранить как» (как transcripts)
    )


@app.delete("/api/voice-memos")
async def api_voice_memos_delete(payload: dict) -> dict:
    """Delete selected voice memos. Body: {"names": [...]}."""
    names = payload.get("names", [])
    if not isinstance(names, list) or not names:
        raise HTTPException(400, "names обязателен (list of file names)")
    res = clean.delete_voice_memos(names)
    return {"ok": True, **res}


@app.post("/api/voice-memos/open-folder")
async def api_voice_memos_open_folder() -> dict:
    """Open the voice-memos folder in the system file manager."""
    d = clean.voice_memos_dir()
    d.mkdir(parents=True, exist_ok=True)
    try:
        _open_in_file_manager(d)
    except Exception as e:
        raise HTTPException(500, f"Не удалось открыть папку: {e}")
    return {"ok": True, "dir": str(d)}


# ---- Translation (v1.5) ----
def _maybe_translate(text: str, info: dict, target_path=None) -> Optional[Path]:
    """Если cfg.translate_to_en и язык != en — переводит и сохраняет *.en.txt.
    Возвращает путь к переведённому файлу, или None.
    Логирует ошибки, но НЕ падает (оригинал уже сохранён).
    Sync — вызывается из producer() (обычная функция в thread executor).
    """
    if not text or not text.strip():
        return None
    if not cfg.get("translate_to_en", False):
        return None
    src_lang = (info.get("language") or "").lower()
    if src_lang in ("en", "en-us", "en-gb", "english", "auto", ""):
        # Нечего переводить — текст уже английский или не знаем
        if src_lang == "":
            log.info("translate_to_en: пропускаю (неизвестный язык)")
        return None
    try:
        translated, used = tr.translate(
            text, target="en",
            provider_name=cfg.get("translation_provider", "minimax"),
            fallback_provider=cfg.get("translation_fallback", "libretranslate"),
            libretranslate_url=cfg.get("libretranslate_url", ""),
            libretranslate_key=cfg.get("libretranslate_key", ""),
            minimax_key=cfg.get("minimax_key", ""),
        )
        info2 = dict(info)
        info2["translation_provider"] = used
        info2["target_language"] = "en"
        if target_path is None:
            # Voice memos / прочее без явного файла — пропускаем перевод
            return None
        return clean.save_translated(target_path, translated, info2)
    except Exception as e:
        log.warning("translate_to_en failed: %s (оригинал сохранён)", e)
        return None


@app.post("/api/translate")
async def api_translate(payload: dict) -> dict:
    """Перевести произвольный текст. Body: {text, target?, source?, provider?, fallback?}.
    Использует config если поля не указаны.
    """
    text = (payload.get("text") or "").strip()
    if not text:
        raise HTTPException(400, "text обязателен")
    target = (payload.get("target") or "en").strip()
    try:
        translated, used = tr.translate(
            text, target=target,
            provider_name=payload.get("provider") or cfg.get("translation_provider", "minimax"),
            fallback_provider=payload.get("fallback") or cfg.get("translation_fallback", "libretranslate"),
            libretranslate_url=payload.get("libretranslate_url", cfg.get("libretranslate_url", "")),
            libretranslate_key=payload.get("libretranslate_key", cfg.get("libretranslate_key", "")),
            minimax_key=payload.get("minimax_key", cfg.get("minimax_key", "")),
        )
        return {"translated": translated, "provider": used, "target": target}
    except Exception as e:
        raise HTTPException(502, f"Ошибка перевода: {e}")


@app.get("/api/translate/providers")
async def api_translate_providers() -> dict:
    """Какие провайдеры перевода доступны прямо сейчас (с таймаутом для Argos)."""
    import asyncio as _aio
    out = []
    for name in ("minimax", "libretranslate", "argos"):
        prov = tr.get_provider(
            name,
            libretranslate_url=cfg.get("libretranslate_url", ""),
            libretranslate_key=cfg.get("libretranslate_key", ""),
            minimax_key=cfg.get("minimax_key", ""),
        )
        if prov is None:
            out.append({"name": name, "available": False,
                        "reason": "MiniMax key не найден" if name == "minimax"
                                  else "не сконфигурирован"})
            continue
        # Проверяем с таймаутом (argos is_available может зависнуть)
        avail_result = [None, None]
        def _check():
            try:
                a, w = prov.is_available()
                avail_result[0], avail_result[1] = a, w
            except Exception as e:
                avail_result[0], avail_result[1] = False, f"exception: {e}"
        t = threading.Thread(target=_check, daemon=True)
        t.start()
        for _ in range(50):
            if not t.is_alive():
                break
            await _aio.sleep(0.1)
        if t.is_alive():
            out.append({"name": name, "available": False,
                        "reason": f"is_available() завис (таймаут 5с). "
                                   f"Скорее всего повреждена установка {name}."})
        else:
            out.append({"name": name, "available": avail_result[0],
                        "reason": avail_result[1] or ""})
    return {"providers": out, "translate_to_en": cfg.get("translate_to_en", False)}


@app.post("/api/translate/install-argos")
async def api_translate_install_argos() -> dict:
    """Устанавливает argostranslate через pip + обе модели en_ru + ru_en.

    Шаги:
      1. pip install argostranslate (если ещё нет)
      2. update_package_index() — обновить индекс моделей с GitHub
      3. установить translate-en_ru (187 МБ) и translate-ru_en (149 МБ) в фоне

    Возвращает сразу {started: true, status: "installing"}, установка идёт
    в фоне. Опрос статуса через /api/translate/providers.
    """
    import asyncio as _aio
    import subprocess as _sp

    # Шаг 1: pip install (argostranslate + langdetect)
    missing_pkgs = []
    try:
        import argostranslate  # noqa: F401
    except ImportError:
        missing_pkgs.append("argostranslate")
    try:
        import langdetect  # noqa: F401
    except ImportError:
        missing_pkgs.append("langdetect")
    if missing_pkgs:
        log.info("Установка пакетов: %s …", ", ".join(missing_pkgs))
        try:
            proc = await _aio.create_subprocess_exec(
                sys.executable, "-m", "pip", "install", "--quiet", *missing_pkgs,
                stdout=_sp.PIPE, stderr=_sp.PIPE,
            )
            try:
                _, stderr = await _aio.wait_for(proc.communicate(), timeout=240)
            except _aio.TimeoutError:
                proc.kill()
                return {"ok": False, "error": f"pip install занял >240с (таймаут). pkgs={missing_pkgs}"}
            if proc.returncode != 0:
                err = stderr.decode("utf-8", "replace")[-500:]
                return {"ok": False, "error": f"pip exit {proc.returncode}: {err}"}
        except Exception as e:
            return {"ok": False, "error": f"pip install: {e}"}
        log.info("Установлены: %s", ", ".join(missing_pkgs))

    # Шаг 2: проверяем какие модели уже стоят
    def _scan_models():
        try:
            from argostranslate import package as _pkg
            _pkg.update_package_index()
            installed = {(p.from_code, p.to_code): p for p in _pkg.get_installed_packages()}
            available = {(p.from_code, p.to_code): p for p in _pkg.get_available_packages()}
            return installed, available, None
        except Exception as e:
            return None, None, str(e)
    scan = [None]
    def _do_scan():
        scan[0] = _scan_models()
    ts = threading.Thread(target=_do_scan, daemon=True)
    ts.start()
    for _ in range(50):
        if not ts.is_alive():
            break
        await _aio.sleep(0.1)
    if ts.is_alive():
        return {"ok": False, "error": "Не удалось просканировать модели (таймаут 5с)"}
    installed, available, err = scan[0]
    if err:
        return {"ok": False, "error": f"Сканирование моделей: {err}"}

    # Шаг 3: качаем недостающие модели в фоне
    to_install = []
    for pair in (("en", "ru"), ("ru", "en")):
        if pair in installed:
            continue
        if pair not in available:
            return {"ok": False, "error": f"Пара {pair[0]}→{pair[1]} отсутствует в индексе пакетов"}
        to_install.append(available[pair])

    if not to_install:
        return {
            "ok": True,
            "already_installed": True,
            "models": [f"{a}→{b}" for (a, b) in installed.keys()],
            "note": "Все языковые пары уже установлены",
        }

    def _bg_install(packages):
        from argostranslate import package as _pkg
        for pkg in packages:
            try:
                log.info("Argos: устанавливаю модель %s→%s (%s) …", pkg.from_code, pkg.to_code, pkg.code)
                pkg.install()
                log.info("Argos: модель %s→%s установлена", pkg.from_code, pkg.to_code)
            except Exception as e:
                log.error("Argos: ошибка установки %s→%s: %s", pkg.from_code, pkg.to_code, e)
    threading.Thread(target=_bg_install, args=(to_install,), daemon=True).start()

    return {
        "ok": True,
        "started": True,
        "installing": [p.code for p in to_install],
        "already_installed": [f"{a}→{b}" for (a, b) in installed.keys()],
        "note": f"Качаю {len(to_install)} модель(и) в фоне (~{sum(187 if p.code == 'translate-en_ru' else 149 for p in to_install)} МБ). " +
                "Следи за /api/translate/providers — когда провайдер станет OK, всё готово.",
    }


# ---- Voice recording session (v1.5) ----
_voice_sessions: dict[str, dict] = {}  # id -> {started_at, chunks: [bytes]}
_voice_lock = threading.Lock()


@app.post("/api/voice/start")
async def api_voice_start() -> dict:
    """Start a new voice recording session. Returns {id, started_at}."""
    sid = secrets.token_urlsafe(8)
    with _voice_lock:
        _voice_sessions[sid] = {
            "started_at": datetime.now().isoformat(timespec="seconds"),
            "chunks": [],
        }
    log.info("Voice session started: %s", sid)
    return {"id": sid, "started_at": _voice_sessions[sid]["started_at"]}


@app.post("/api/voice/chunk")
async def api_voice_chunk(
    id: str = Form(...),
    chunk: UploadFile = File(...),
) -> dict:
    """Append an audio chunk to the active session.
    `chunk` is a small audio/webm (Opus) blob from MediaRecorder timeslice.
    """
    with _voice_lock:
        sess = _voice_sessions.get(id)
        if not sess:
            raise HTTPException(404, f"Сессия '{id}' не найдена или истекла")
        data = await chunk.read()
        sess["chunks"].append(data)
    return {"id": id, "received_bytes": len(data), "total_chunks": len(sess["chunks"])}


@app.post("/api/voice/stop")
async def api_voice_stop(payload: dict) -> dict:
    """Finalize a voice recording session: concatenate chunks → transcribe → save.
    Body: {"id": "...", "language": "ru"}
    Returns: {"text": str, "file": str, "duration_sec": float}
    """
    sid = payload.get("id")
    if not sid or not isinstance(sid, str):
        raise HTTPException(400, "id обязателен")
    language = payload.get("language") or cfg.get("language", "ru")
    with _voice_lock:
        sess = _voice_sessions.pop(sid, None)
    if not sess:
        raise HTTPException(404, f"Сессия '{sid}' не найдена или истекла")
    chunks = sess["chunks"]
    if not chunks:
        raise HTTPException(400, "Сессия пуста — нет ни одного чанка")
    # Сохраняем в temp webm, конвертируем в wav через ffmpeg
    tmp_webm = tempfile.NamedTemporaryFile(delete=False, suffix=".webm")
    tmp_webm_path = Path(tmp_webm.name)
    tmp_webm.write(b"".join(chunks))
    tmp_webm.close()
    audio_path = tmp_webm_path
    try:
        try:
            audio_path = _extract_audio(tmp_webm_path)
        except Exception as e:
            log.warning("ffmpeg convert failed, trying direct webm: %s", e)
            audio_path = tmp_webm_path
        p_name = cfg.get("provider")
        m_name = cfg.get("model")
        dev = cfg.get("device")
        p = registry.get(p_name)
        if p is None:
            raise HTTPException(500, f"Провайдер '{p_name}' не найден")
        if not (p.is_available()[0]):
            raise HTTPException(500, f"Провайдер '{p_name}' не установлен")
        # lazy-load
        global _loaded_provider, _loaded_model, _loaded_device
        if not (_loaded_provider == p_name and _loaded_model == m_name and _loaded_device == dev):
            if not p.is_model_downloaded(m_name):
                raise HTTPException(404, f"Модель {m_name} не скачана")
            log.info("Lazy-loading %s/%s on %s …", p_name, m_name, dev)
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, lambda: p.load(m_name, device=dev))
            _loaded_provider, _loaded_model, _loaded_device = p_name, m_name, dev
        out = p.transcribe(audio_path, language)
        text = out.get("text", "")
        info = out.get("info", {}) or {}
        info.setdefault("provider", p_name)
        info.setdefault("model", m_name)
        # Передаём segments в save_voice_memo — пишутся в sidecar
        # <stem>.segments.json для последующего экспорта в SRT/VTT/JSON.
        _voice_segs = out.get("segments") or []
        path = clean.save_voice_memo(text, info, segments=_voice_segs)
        translation_text = None
        translation_provider = None
        if path:
            tpath = _maybe_translate(text, info, target_path=path)
            if tpath and tpath.is_file():
                # Прочитать .en.txt (без шапки) для UI
                try:
                    raw = tpath.read_text(encoding="utf-8")
                    # strip header (# комментарии) — оставить только текст
                    lines = [ln for ln in raw.splitlines() if not ln.startswith("#")]
                    translation_text = "\n".join(lines).strip()
                    translation_provider = info.get("translation_provider", "argos")
                except Exception as e:
                    log.warning("не удалось прочитать %s: %s", tpath, e)
        log.info("Voice memo saved: %s (chunks=%d)", path.name, len(chunks))
        return {
            "id": sid,
            "text": text,
            "file": path.name,
            "dir": str(clean.voice_memos_dir()),
            "translation": translation_text,
            "translation_provider": translation_provider,
        }
    except HTTPException:
        raise
    except Exception as e:
        log.exception("Voice stop failed (sid=%s, chunks=%d)", sid, len(chunks))
        raise HTTPException(500, f"Ошибка расшифровки: {type(e).__name__}: {e}")
    finally:
        if audio_path != tmp_webm_path:
            try:
                audio_path.unlink()
            except OSError:
                pass
        try:
            tmp_webm_path.unlink()
        except OSError:
            pass


# ---- Providers ----
@app.get("/api/providers")
async def api_providers() -> dict:
    out = []
    for p in registry.all():
        avail, why = p.is_available()
        out.append({
            "name": p.info.name,
            "display_name": p.info.display_name,
            "description": p.info.description,
            "requires_gpu": p.info.requires_gpu,
            "installed": avail,
            "reason": why,
            "install_hint": p.info.install_hint,
            "default_model": p.info.default_model,
            "models": p.list_models(),
            "languages": p.info.languages,
            "homepage": p.info.homepage,
        })
    return {"providers": out, "active": {
        "provider": cfg.get("provider"),
        "model": cfg.get("model"),
        "device": cfg.get("device"),
    }}


@app.post("/api/provider/install")
async def api_provider_install(payload: dict) -> dict:
    name = payload.get("provider")
    if not name:
        raise HTTPException(400, "provider required")
    try:
        p = registry.get(name)
    except KeyError:
        raise HTTPException(404, f"Провайдер '{name}' не найден. "
                                 f"Доступные: {registry.names()}")
    log_cb = []
    # Run the install off the event loop: pip can take minutes and must not
    # freeze the whole server (health/providers/etc. would all time out).
    loop = asyncio.get_event_loop()
    ok = await loop.run_in_executor(
        None, lambda: p.install(on_log=lambda m: log_cb.append(m))
    )
    return {"ok": ok, "log": log_cb[-50:]}


@app.post("/api/provider/load")
async def api_provider_load(payload: dict) -> dict:
    name = payload.get("provider") or cfg.get("provider")
    model = payload.get("model") or cfg.get("model")
    device = payload.get("device") or cfg.get("device")
    if not name or not model:
        raise HTTPException(400, "provider and model required")
    try:
        p = registry.get(name)
    except KeyError:
        raise HTTPException(404, f"Провайдер '{name}' не найден. "
                                 f"Доступные: {registry.names()}")
    avail, why = p.is_available()
    if not avail:
        raise HTTPException(412, f"Провайдер не готов: {why}")

    if not p.is_model_downloaded(model):
        raise HTTPException(404, f"Модель {model} не скачана. "
                                  f"Скачайте через /api/model/download")

    log.info("Loading %s/%s on %s", name, model, device)
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, lambda: p.load(model, device=device))
    cfg.set("provider", name)
    cfg.set("model", model)
    cfg.set("device", device)

    global _loaded_provider, _loaded_model, _loaded_device
    _loaded_provider, _loaded_model, _loaded_device = name, model, device
    return {"ok": True, "loaded": {"provider": name, "model": model, "device": device}}


# ---- Model management ----
@app.get("/api/model/check")
async def api_model_check(provider: str, model: str) -> dict:
    try:
        p = registry.get(provider)
    except KeyError:
        raise HTTPException(404, f"Провайдер '{provider}' не найден. "
                                 f"Доступные: {registry.names()}")
    return p.check_model_update(model)


@app.post("/api/model/download")
async def api_model_download(payload: dict) -> StreamingResponse:
    provider = payload.get("provider")
    model = payload.get("model")
    if not provider or not model:
        raise HTTPException(400, "provider and model required")
    try:
        p = registry.get(provider)
    except KeyError:
        raise HTTPException(404, f"Провайдер '{provider}' не найден. "
                                 f"Доступные: {registry.names()}")

    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_event_loop()

    def _enqueue(kind: str, percent: int, payload: Any) -> None:
        try:
            loop.call_soon_threadsafe(queue.put_nowait, (kind, percent, payload))
        except RuntimeError:
            pass

    def producer() -> None:
        try:
            # download_model calls on_progress(percent, message) — adapt to SSE events.
            def on_progress(percent: float, message: str) -> None:
                _enqueue("progress", int(percent), message)
            path = p.download_model(model, on_progress=on_progress)
            _enqueue("done", 100, str(path))
        except Exception as e:
            _enqueue("error", 0, f"{type(e).__name__}: {e}")

    loop.run_in_executor(None, producer)

    async def stream():
        while True:
            kind, percent, payload = await queue.get()
            evt = json.dumps({"type": kind, "percent": percent, "payload": payload},
                             ensure_ascii=False)
            yield f"data: {evt}\n\n"
            if kind in ("done", "error"):
                break

    return StreamingResponse(
        stream(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---- Updates ----
@app.get("/api/updates")
async def api_updates(stream: int = 0) -> Any:
    """Check app + model updates.

    Default: single JSON (backward-compatible).
    `?stream=1`: SSE — emits `progress` events per checked item, then `done` with the full report.
    """
    if not stream:
        return upd.check_all_updates()

    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_event_loop()

    def _enqueue(kind: str, percent: int, payload: Any) -> None:
        try:
            loop.call_soon_threadsafe(queue.put_nowait, (kind, percent, payload))
        except RuntimeError:
            pass

    def worker() -> None:
        try:
            def on_progress(m: dict) -> None:
                if m.get("phase") == "model":
                    log.info("Update check %d/%d: %s", m["done"], m["total"], m["label"])
                _enqueue("progress", m.get("percent", 0), m)
            report = upd.check_all_updates(on_progress=on_progress)
            _enqueue("done", 100, report)
        except Exception as e:
            log.exception("Update check failed")
            _enqueue("error", 0, f"{type(e).__name__}: {e}")

    loop.run_in_executor(None, worker)

    async def stream_gen():
        while True:
            kind, percent, payload = await queue.get()
            evt = json.dumps({"type": kind, "percent": percent, "payload": payload},
                             ensure_ascii=False)
            yield f"data: {evt}\n\n"
            if kind in ("done", "error"):
                break

    return StreamingResponse(
        stream_gen(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/updates/app")
async def api_update_app() -> dict:
    """Применить self-update (git pull + pip upgrade). DEPRECATED — use /api/updates/apply."""
    return upd.run_full_update()


# ---- v1.5.8 — Real auto-update endpoints ----

import os as _os  # for restart
import threading as _threading
from tools import update_state as _ustate

_update_lock = _threading.Lock()  # single concurrent apply


@app.get("/api/updates/state")
async def api_updates_state() -> dict:
    """Current update state (для UI banner + auto-apply logic).

    Returns:
        {
            "current_version": "f843bdb",
            "latest_version": "abc1234",
            "available": true,
            "should_notify": true,    # есть обновление И юзер не нажал Later
            "dismissed_version": null,
            "last_check": "2026-08-20T...",
            "last_apply_at": null,
            "last_apply_result": null,
            "last_apply_version": null,
            "check_error": null,
            "auto_update_enabled": false  # из config
        }
    """
    state = _ustate.get()
    return {
        **state,
        "should_notify": _ustate.should_notify(),
        "auto_update_enabled": bool(cfg.get("auto_update_app", False)),
    }


@app.post("/api/updates/check-now")
async def api_updates_check_now() -> dict:
    """Принудительная проверка обновлений (force check). Возвращает state."""
    if not _update_lock.acquire(timeout=2):
        raise HTTPException(409, "Update check already running")
    try:
        from tools.update import current_version, latest_version
        current = current_version()
        latest = latest_version()
        if latest is None:
            _ustate.mark_checked(current, None, available=False,
                                  error="Failed to fetch origin (network?)")
            return _ustate.get()
        available = (current != "unknown" and current != latest)
        _ustate.mark_checked(current, latest, available=available)
        log.info("Update check: current=%s latest=%s available=%s", current, latest, available)
        return _ustate.get()
    finally:
        _update_lock.release()


@app.post("/api/updates/dismiss")
async def api_updates_dismiss() -> dict:
    """Юзер нажал 'Later' — скрыть banner до появления новой версии."""
    state = _ustate.get()
    latest = state.get("latest_version")
    if latest:
        _ustate.mark_dismissed(latest)
    return {"ok": True, "dismissed_version": latest}


@app.post("/api/updates/apply")
async def api_updates_apply() -> dict:
    """Apply update: git pull + pip upgrade. Saves state. Optionally restarts.

    Returns immediately with {ok, new_version, restart: bool}.
    Restart happens via _os.execv() на фоне — клиент увидит «server restarting» и обновит страницу.
    """
    if not _update_lock.acquire(timeout=2):
        raise HTTPException(409, "Update apply already running")

    from tools.update import current_version, app_pull, deps_upgrade
    try:
        current = current_version()
        log.info("Apply update: current=%s, applying…", current)

        # git pull
        pull = app_pull()
        if not pull.get("ok"):
            _ustate.mark_applied(current, "git_failed")
            raise HTTPException(500, f"git pull failed: {pull.get('detail', pull)}")

        # pip install
        deps = deps_upgrade()
        if not deps.get("ok"):
            _ustate.mark_applied(current, "pip_failed")
            raise HTTPException(500, f"pip upgrade failed: {deps.get('detail', deps)}")

        _ustate.mark_applied(current, "ok")

        # Определить новую версию
        new_version = current_version()

        # Если auto_update_app — restart. Иначе — пусть юзер сам решит.
        if cfg.get("auto_update_app", False):
            log.info("Auto-update: restarting server in 1.5s …")
            import threading as _t
            def _restart_after():
                time.sleep(1.5)
                try:
                    _os.execv(sys.executable, [sys.executable] + sys.argv)
                except Exception as e:
                    log.error("Restart failed: %s — exit so watchdog can pick up", e)
                    _os._exit(0)
            _t.Thread(target=_restart_after, daemon=True, name="autrau-restart").start()
            return {
                "ok": True,
                "old_version": current,
                "new_version": new_version,
                "restart": True,
                "restart_in_sec": 1.5,
            }

        # Manual mode — без restart, юзер сам решит
        return {
            "ok": True,
            "old_version": current,
            "new_version": new_version,
            "restart": False,
        }
    finally:
        _update_lock.release()


# ---- Transcribe ----
@app.post("/transcribe")
async def transcribe(
    file: UploadFile = File(...),
    language: str = Form("ru"),
    provider: Optional[str] = Form(None),
    model: Optional[str] = Form(None),
    device: Optional[str] = Form(None),
) -> StreamingResponse:
    # Decide provider+model
    p_name = provider or cfg.get("provider")
    m_name = model or cfg.get("model")
    dev = device or cfg.get("device")
    if not p_name or not m_name:
        raise HTTPException(400, "Не выбран провайдер/модель")

    try:
        p = registry.get(p_name)
    except KeyError:
        raise HTTPException(404, f"Провайдер '{p_name}' не найден. "
                                 f"Доступные: {registry.names()}")
    avail, why = p.is_available()
    if not avail:
        raise HTTPException(412, why)

    # Lazy-load if needed
    global _loaded_provider, _loaded_model, _loaded_device
    if _loaded_lock is None:
        raise HTTPException(503, "Server still starting")
    async with _loaded_lock:
        if not (_loaded_provider == p_name and _loaded_model == m_name
                and _loaded_device == dev):
            if not p.is_model_downloaded(m_name):
                raise HTTPException(404, f"Модель {m_name} не скачана")
            log.info("Lazy-loading %s/%s on %s …", p_name, m_name, dev)
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, lambda: p.load(m_name, device=dev))
            _loaded_provider, _loaded_model, _loaded_device = p_name, m_name, dev

    # Save upload (с проверкой лимита MAX_UPLOAD_MB)
    suffix = Path(file.filename or "audio").suffix or ".audio"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp_path = Path(tmp.name)
    total = 0
    try:
        with tmp:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_UPLOAD_MB * 1024 * 1024:
                    raise HTTPException(
                        413,
                        f"Файл {total / 1024 / 1024:.0f} МБ больше лимита "
                        f"{MAX_UPLOAD_MB} МБ. Уменьшите файл или поднимите MAX_UPLOAD_MB.",
                    )
                tmp.write(chunk)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
    log.info("Saved upload to %s (%d bytes)", tmp_path, total)

    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_event_loop()

    def _enqueue(kind: str, percent: int, payload: Any) -> None:
        try:
            loop.call_soon_threadsafe(queue.put_nowait, (kind, percent, payload))
        except RuntimeError:
            pass

    def producer() -> None:
        audio_path = tmp_path
        try:
            if tmp_path.suffix.lower() in VIDEO_EXTS:
                def _on_audio_pct(percent: int, text: str) -> None:
                    _enqueue("progress", percent, {"text": text})
                audio_path = _extract_audio(tmp_path, on_progress=_on_audio_pct)

            def on_seg(seg: Segment, percent: int) -> None:
                _enqueue("progress", percent, seg.__dict__)

            out = p.transcribe(audio_path, language or cfg.get("language", "ru"),
                               on_segment=on_seg)
            try:
                _info = out.get("info", {}) or {}
                _info.setdefault("provider", p_name)
                _info.setdefault("model", m_name)
                # Передаём segments в save_transcript — пишутся в sidecar
                # <stem>.segments.json для последующего экспорта в SRT/VTT/JSON.
                _segs = out.get("segments") or []
                _path = clean.save_transcript(
                    file.filename, out.get("text", ""), _info, segments=_segs,
                )
                # Сообщим клиенту имя файла, чтобы работал /api/transcripts/{name}/export
                if _path:
                    out["file"] = _path.name
                if _path:
                    tpath = _maybe_translate(out.get("text", ""), _info, target_path=_path)
                    if tpath and tpath.is_file():
                        # Прочитать .en.txt (без шапки) и положить в out
                        try:
                            raw = tpath.read_text(encoding="utf-8")
                            lines = [ln for ln in raw.splitlines() if not ln.startswith("#")]
                            out["translation"] = "\n".join(lines).strip()
                            out["translation_provider"] = _info.get("translation_provider", "argos")
                        except Exception:
                            pass
            except Exception as se:
                log.warning("Не удалось сохранить расшифровку: %s", se)
            _enqueue("done", 100, out)
        except Exception as e:
            log.exception("Transcribe failed")
            _enqueue("error", 0, f"{type(e).__name__}: {e}")
        finally:
            if audio_path != tmp_path:
                try:
                    os.unlink(audio_path)
                except OSError:
                    pass
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    loop.run_in_executor(None, producer)

    async def stream():
        try:
            while True:
                kind, percent, payload = await queue.get()
                evt = json.dumps({"type": kind, "percent": percent, "payload": payload},
                                 ensure_ascii=False)
                yield f"data: {evt}\n\n"
                if kind in ("done", "error"):
                    break
        except asyncio.CancelledError:
            log.info("Client disconnected")
            raise

    return StreamingResponse(
        stream(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no",
                 "Connection": "keep-alive"},
    )


# ---- entry point ----

if __name__ == "__main__":
    import uvicorn
    log.info("Autrau starting on http://%s:%d", HOST, PORT)
    # Предполётная проверка translation providers (СИНХРОННАЯ, чтобы появилась в логе
    # ДО старта uvicorn и lifespan-тасков). Если argos не работает — авто-установка в фоне.
    log.info("─" * 60)
    log.info("🌐 TRANSLATION PROVIDERS (preflight)")
    log.info("─" * 60)
    try:
        cfg.init()
        _preflight_argos_needs_install = False
        for name in ("minimax", "libretranslate", "argos"):
            prov = tr.get_provider(
                name,
                libretranslate_url=cfg.get("libretranslate_url", ""),
                libretranslate_key=cfg.get("libretranslate_key", ""),
                minimax_key=cfg.get("minimax_key", ""),
            )
            if prov is None:
                log.info("  ✗ %-14s  не сконфигурирован", name)
                continue
            a, w = prov.is_available()
            if a:
                log.info("  ✓ %-14s  OK", name)
            else:
                log.info("  ✗ %-14s  %s", name, w or "недоступен")
                if name == "argos" and ("pip install" in (w or "") or "модели отсутствуют" in (w or "")):
                    _preflight_argos_needs_install = True
        if _preflight_argos_needs_install:
            log.info("🔧 argos не работает → авто-установка в фоне (pip + модели, ~336 МБ)")
            threading.Thread(target=_bg_install_argos, daemon=True).start()
    except Exception as _e:
        log.warning("preflight translation check: %s", _e)
    log.info("─" * 60)
    log.info("Open the UI at:  http://%s:%d/", HOST, PORT)
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")
