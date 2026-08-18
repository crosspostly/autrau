# Autrau — Project Context

## What This Is

**Autrau** — локальный десктопный транскрибатор аудио/видео. Запускается как FastAPI-сервер на `localhost:8000` (стартует через `start.bat`). Никакого облака, никакой авторизации, никаких лимитов — всё работает на CPU/GPU пользователя. Опубликован как портативное приложение на GitHub: https://github.com/crosspostly/autrau.

UI — единый `index.html` (vanilla JS, без фреймворков) с тёмной темой в стиле Handi/Notion. Сервер на FastAPI + uvicorn, Python 3.13.

## Core Value

**Локальная приватная транскрибация с несколькими провайдерами на выбор.** Пользователь сам выбирает, какую модель гонять: faster-whisper, whisper-cpp, parakeet-tdt (NeMo, NVIDIA) или parakeet-tdt-onnx (DirectML/AMD). Все настройки и расшифровки — локальные файлы в `data/`.

## Tech Stack

- **Backend**: Python 3.13, FastAPI, uvicorn, providers (Whisper.cpp via pywhispercpp, Faster-Whisper, Parakeet NeMo, Parakeet ONNX/DirectML)
- **Frontend**: vanilla HTML/CSS/JS, без сборки, единый файл `index.html`
- **Transcription models**: tiny/large-v3 (whisper), parakeet-tdt-0.6b-v3 (ONNX int8 ~640MB)
- **Config**: `data/config.json` (gitignored, локальный), `tools/config.py` (defaults)
- **Auto-cleanup**: фоновый asyncio-loop в `server.py` каждые 6 часов удаляет транскрипты старше N дней
- **Distribution**: GitHub releases + Handy-style portable target (в работе)
- **CI**: GitHub Actions на push/PR

## Repository Layout

```
autrau/
├── index.html              # UI (vanilla JS, всё inline)
├── server.py               # FastAPI server + endpoints + streaming
├── providers/              # Pluggable transcription providers
│   ├── base.py             # Abstract Provider class
│   ├── whisper_cpp.py      # pywhispercpp wrapper
│   ├── faster_whisper.py   # CTranslate2 wrapper
│   ├── parakeet.py         # NVIDIA NeMo (CUDA only)
│   └── parakeet_onnx.py    # ONNX/DirectML (any GPU/CPU)
├── tools/
│   ├── config.py           # config load/save + defaults
│   ├── cleanup.py          # save_transcript, list_transcripts, run_cleanup
│   ├── favorites.py        # star-marked files (protected from cleanup)
│   ├── check.py            # health check + version report
│   └── updates.py          # git pull + pip upgrade
├── data/                   # gitignored runtime state
│   ├── config.json         # local user config
│   ├── transcripts/        # saved .txt files
│   └── models/             # downloaded model files
├── static/                 # favicon, etc.
├── docs/                   # ROADMAP.md, CONFIGURATION.md
├── start.bat               # main launcher (venv + python -m uvicorn)
├── update.bat              # git pull + pip upgrade
└── publish.bat             # publish release to GitHub
```

## Key Architectural Decisions

- **No framework for UI** — vanilla JS keeps `index.html` self-contained and easy to grep. Build step is forbidden.
- **Streaming via SSE** — `/transcribe` returns `StreamingResponse` with event types `progress`, `segment`, `done`, `error` so the UI can show live transcription.
- **Lazy model loading** — модель грузится при первой расшифровке, не при старте сервера. На повторных вызовах — переиспользуется.
- **Provider plugin system** — все 4 провайдера реализуют `Provider` (base.py), регистрируются в `providers/__init__.py`. `is_available()` определяет, показывать ли в UI.
- **Config.json is gitignored** — локальные настройки пользователя. Defaults — в `tools/config.py`. Важно: при деплое `config.json` не перезаписывается, поэтому «исторические» баги вроде banned-ориентиров в статьях прилетали именно оттуда.
- **Server runs on WindowsApps Python 3.13** (`C:\Program Files\WindowsApps\...`), не на MS Store Python. `python` в PATH = WindowsApps stub. Разработка — в `.venv`, сервер — в WindowsApps.
- **Tests in `.gitignore`** — локальные `_test_*.py`, `_api_check*.py`, `tests/_*` — не для репо.
- **Provider filtering в UI** — не-установленные провайдеры скрыты из дропдауна; faster-whisper скрыт явно (CPU-only, бесполезен на AMD).

## Current Milestone: v1.5 — Handi-like UX

**Goal:** превратить Autrau в «Handi-стайл» desktop-transcription: реал-тайм запись по хоткею, автоперевод, голосовые заметки как отдельный раздел.

**Target features:**

1. ✅ **Расширение исходного файла в имени транскрипта** — `voice-123.mp3` → `2026-08-18_voice-123.mp3.txt` (вместо `2026-08-18_voice-123.txt`)
2. ✅ **Размер в КБ если < 1 МБ** — раньше `0.0 МБ` показывалось для маленьких файлов
3. 🔄 **Горячие клавиши для записи в реальном времени (Handi-style)** — настраиваемое сочетание клавиш, по нажатию — запись микрофона + реал-тайм транскрипция
4. 🔄 **Автоперевод на английский** — галочка в настройках, после транскрипции — перевод `ru→en`
5. 🔄 **Вкладка «Голосовые заметки»** — отдельная категория в секции расшифровок для записей, сделанных хоткеем

## Active Requirements

См. [REQUIREMENTS.md](REQUIREMENTS.md) для полного списка с REQ-IDs.

## Out of Scope (текущий milestone)

- Portable exe (PyInstaller) — отдельный крупный проект
- iOS / Android клиент
- Sync между устройствами
- Speaker diarization (кто говорит)
- Real-time translation (streaming)

## Key Decisions Log

См. раздел "Decisions" в каждой фазе, или `docs/ROADMAP.md`.

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---

*Last updated: 2026-08-19 (start of v1.5 milestone)*
