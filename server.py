"""Autrau — local multi-provider audio transcription server.

Endpoints:
  GET  /                          UI
  GET  /health                    quick health probe
  GET  /api/providers             list providers + status + model list
  GET  /api/config                current config
  POST /api/config                update config
  GET  /api/updates               check app + model updates
  POST /api/updates/app           run self-update (git pull + pip upgrade)
  POST /api/model/download        download a model for a provider (SSE progress)
  POST /api/model/check           check update for one model
  POST /api/provider/load         (re)load provider+model into memory
  POST /transcribe                main endpoint, streams SSE progress

Env:  AUTRAU_PORT, AUTRAU_HOST (defaults 8000, 127.0.0.1)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

# Add project root to path so `providers` and `tools` resolve when started directly
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from providers import registry  # noqa: E402
from providers.base import Segment  # noqa: E402
import tools.config as cfg  # noqa: E402
import tools.check as check  # noqa: E402
import tools.update as upd  # noqa: E402

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger("autrau.server")

HOST = os.environ.get("AUTRAU_HOST", "127.0.0.1")
PORT = int(os.environ.get("AUTRAU_PORT", "8000"))
MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "500"))

# ---- App ----
app = FastAPI(title="Autrau", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_origin_regex=".*",
    allow_methods=["*"],
    allow_headers=["*"],
)
STATIC_DIR = PROJECT_ROOT

# In-memory loaded model state
_loaded_lock = asyncio.Lock()
_loaded_provider: Optional[str] = None
_loaded_model: Optional[str] = None
_loaded_device: Optional[str] = None


@app.on_event("startup")
async def on_startup() -> None:
    cfg.init()
    if cfg.get("check_updates_on_start"):
        log.info("Startup update check (background) …")
        asyncio.create_task(_startup_check())


async def _startup_check() -> None:
    try:
        report = upd.check_all_updates()
        if report.get("app", {}).get("has_update"):
            log.warning("App update available. Run update.bat or call /api/updates/app")
    except Exception as e:
        log.warning("Startup check failed: %s", e)


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


# ---- Providers ----
@app.get("/api/providers")
async def api_providers() -> dict:
    out = []
    for p in registry.all():
        avail, why = p.is_available()
        out.append({
            "name": p.info.name,
            "display": p.info.display_name,
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
    p = registry.get(name)
    log_cb = []
    ok = p.install(on_log=lambda m: log_cb.append(m))
    return {"ok": ok, "log": log_cb[-50:]}


@app.post("/api/provider/load")
async def api_provider_load(payload: dict) -> dict:
    name = payload.get("provider") or cfg.get("provider")
    model = payload.get("model") or cfg.get("model")
    device = payload.get("device") or cfg.get("device")
    if not name or not model:
        raise HTTPException(400, "provider and model required")

    p = registry.get(name)
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
    p = registry.get(provider)
    return p.check_model_update(model)


@app.post("/api/model/download")
async def api_model_download(payload: dict) -> StreamingResponse:
    provider = payload.get("provider")
    model = payload.get("model")
    if not provider or not model:
        raise HTTPException(400, "provider and model required")
    p = registry.get(provider)

    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_event_loop()

    def _enqueue(kind: str, percent: int, payload: Any) -> None:
        try:
            loop.call_soon_threadsafe(queue.put_nowait, (kind, percent, payload))
        except RuntimeError:
            pass

    def producer() -> None:
        try:
            path = p.download_model(model, on_progress=_enqueue)
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
async def api_updates() -> dict:
    return upd.check_all_updates()


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

    p = registry.get(p_name)
    avail, why = p.is_available()
    if not avail:
        raise HTTPException(412, why)

    # Lazy-load if needed
    global _loaded_provider, _loaded_model, _loaded_device
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
        try:
            def on_seg(seg: Segment, percent: int) -> None:
                _enqueue("progress", percent, seg.__dict__)

            out = p.transcribe(tmp_path, language or cfg.get("language", "ru"),
                               on_segment=on_seg)
            _enqueue("done", 100, out)
        except Exception as e:
            log.exception("Transcribe failed")
            _enqueue("error", 0, f"{type(e).__name__}: {e}")
        finally:
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
