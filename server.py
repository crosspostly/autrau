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
import shutil
import subprocess
import sys
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse

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

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger("autrau.server")

HOST = os.environ.get("AUTRAU_HOST", "127.0.0.1")
PORT = int(os.environ.get("AUTRAU_PORT", "8000"))
MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "500"))

# Video containers — перед распознаванием у них извлекается аудиодорожка (ffmpeg).
VIDEO_EXTS = {
    ".mp4", ".m4v", ".mkv", ".mov", ".avi", ".webm",
    ".flv", ".wmv", ".mpg", ".mpeg", ".ts", ".mts", ".3gp",
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
    if cfg.get("check_updates_on_start"):
        log.info("Startup update check (background) …")
        asyncio.create_task(_startup_check())
    asyncio.create_task(_cleanup_loop())
    yield
    # Shutdown: nothing to clean up — provider instances hold their own resources.


async def _startup_check() -> None:
    try:
        report = upd.check_all_updates()
        if report.get("app", {}).get("has_update"):
            log.warning("App update available. Run update.bat or call /api/updates/app")
    except Exception as e:
        log.warning("Startup check failed: %s", e)


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


def _extract_audio(video_path: Path) -> Path:
    """Извлечь аудиодорожку из видео в 16 кГц моно WAV (через ffmpeg)."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError(
            "для видео нужен ffmpeg — установите его и перезапустите приложение"
        )
    out = Path(f"{video_path}.wav")
    proc = subprocess.run(
        [ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
         "-i", str(video_path), "-vn", "-ac", "1", "-ar", "16000", str(out)],
        capture_output=True, text=True, timeout=600,
    )
    if proc.returncode != 0 or not out.is_file():
        raise RuntimeError(
            f"не удалось извлечь звук из видео (ffmpeg): {proc.stderr.strip()[-300:]}"
        )
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
    return upd.run_full_update()


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

    # Save upload
    suffix = Path(file.filename or "audio").suffix or ".audio"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = Path(tmp.name)
    log.info("Saved upload to %s (%d bytes)", tmp_path, len(content))

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
                _enqueue("progress", 0, {"text": "🎬 извлекаю звук из видео …"})
                audio_path = _extract_audio(tmp_path)

            def on_seg(seg: Segment, percent: int) -> None:
                _enqueue("progress", percent, seg.__dict__)

            out = p.transcribe(audio_path, language or cfg.get("language", "ru"),
                               on_segment=on_seg)
            try:
                clean.save_transcript(file.filename, out.get("text", ""),
                                      out.get("info", {}))
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
    log.info("Open the UI at:  http://%s:%d/", HOST, PORT)
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")
