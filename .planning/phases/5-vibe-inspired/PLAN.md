---
phase: 5
name: vibe-inspired-quick-wins
version: v1.5.7
status: in_progress
started: 2026-08-19
estimated: 4-5 hours
---

# Phase 5 PLAN — Vibe-inspired quick wins (v1.5.7)

**Анализ:** `C:\obsidian\04_Knowledge\wiki\open-source-vibe-analysis.md`
**Stack:** Python 3.13 + FastAPI + vanilla JS (не меняем)

## Sub-phases

### 5.1 — CLI tool `python -m autrau.cli` (~45 min) [REQ-v1.5.7-001]

**Goal:** Использовать autrau из терминала.

**Команды:**
```bash
# Транскрибировать один файл
python -m autrau.cli transcribe file.mp3 --language ru --output out.txt

# Пакетная обработка директории
python -m autrau.cli batch ./audio/ --pattern "*.mp3" --output ./transcripts/

# Список провайдеров
python -m autrau.cli providers

# Список моделей провайдера
python -m autrau.cli models --provider whisper-cpp

# Версия + статус сервера
python -m autrau.cli status
```

**Files:**
- `tools/cli.py` (новый) — argparse + delegating to existing functions
- `pyproject.toml` или `setup.py` — entry point `autrau = tools.cli:main`

**Reuse:** использует существующие `clean.save_transcript`, `transcribe.uploaded_file` (если есть) или прямой вызов через HTTP к localhost.

**Tests:** `_test_cli.py` (gitignored) — invoke each subcommand, verify exit code + output.

### 5.2 — yt-dlp endpoint `POST /api/yt-dlp?url=...` (~1 hour) [REQ-v1.5.7-002]

**Goal:** Скачать аудио по URL → транскрибировать.

**Endpoints:**
- `POST /api/yt-dlp` body `{url, language?, model?, provider?}` → SSE stream прогресса + финальный transcript
- `GET /api/yt-dlp/info?url=...` → `{title, duration, thumbnail}` (UI preview без скачивания)

**Поддерживаемые сайты:** YouTube, Vimeo, Twitter/X, Facebook, Twitch clips, Reddit, SoundCloud, ~1000+ других (через yt-dlp).

**Files:**
- `tools/yt_dlp.py` (новый) — обёртка над `yt_dlp` Python API
- `server.py` — endpoints + SSE progress
- `index.html` — UI: кнопка «🔗 Из URL» + input

**Dep:** `yt-dlp` (добавить в `requirements.txt`)
**E2E test:** скачать 30-сек YouTube клип → транскрибировать → проверить .txt на диске.

### 5.3 — System audio loopback (Windows WASAPI) (~2 hours) [REQ-v1.5.7-003]

**Goal:** Захват системного звука (что играет в колонках) — YouTube, Zoom, etc.

**Endpoints:**
- `POST /api/system-audio/start` → начинает захват (пока без транскрибации, копит в буфер)
- `POST /api/system-audio/stop` → стоп, транскрибирует, возвращает result

**Lib:** `soundcard` (cross-platform, supports WASAPI loopback) или `pyaudiowpatch` (Windows only, проще).

**План:**
1. `pip install soundcard` в venv
2. `tools/system_audio.py` — class Recorder с `start()`, `stop() → wav_bytes`
3. `server.py` — endpoints, single instance lock (нельзя два одновременно)
4. UI: кнопка «🔊 Системный звук» (рядом с «🎤 Микрофон»)

**Note:** Только Windows изначально. macOS/Linux требуют других бэкендов (в v1.6+).

**E2E test:** воспроизвести test_audio.wav в фоне → system-audio/start → подождать 5 сек → system-audio/stop → проверить транскрипт.

### 5.4 — Swagger UI `/docs` (~10 min) [REQ-v1.5.7-004]

**Goal:** FastAPI auto-docs. Проверить что `/docs` и `/openapi.json` работают.

**Action:** `curl http://127.0.0.1:8000/docs` — должен вернуть 200 HTML.

**Edge case:** если в `server.py` app создаётся через `FastAPI(...)` напрямую (не `__call__`), Swagger уже работает. Если нет — поправить.

**Files:** только verify, никаких изменений (если OK).

### 5.5 — AGENTS.md update (~30 min) [REQ-v1.5.7-005]

**Goal:** Скопировать полезное из vibe/AGENTS.md + autrau-специфичное.

**Sections:**
- Package managers (Windows-специфика: `py -3.13` vs `python`, `pip` vs `py -3.13 -m pip`)
- Validation scripts (Python scripts in `tests/` или `plans/`)
- Task routing (subprocess, PowerShell gotchas)
- Obsidian notes integration (C:\obsidian\...)
- Memory (autrau-specific lessons learned)

**File:** `.planning/AGENTS.md` (overwrite + add new sections)

---

## Commit strategy

5 коммитов (по одному на sub-phase), либо 1 большой если sub-phases small:
- `v1.5.7.1: CLI tool (python -m autrau.cli)`
- `v1.5.7.2: yt-dlp endpoint + UI`
- `v1.5.7.3: system audio loopback (Windows WASAPI)`
- `v1.5.7.4: verify Swagger UI at /docs`
- `v1.5.7.5: AGENTS.md update (autrau-specific patterns)`

Push после каждого коммита.

## Risks

- **yt-dlp install size** — ~10 МБ, ok
- **soundcard on Windows** — может потребовать admin права для установки. Fallback на `pyaudiowpatch` если `soundcard` не работает.
- **CLI confuses with autrau run** — разные entry points, не должно конфликтовать

## Done criteria

- [ ] `python -m autrau.cli transcribe test.mp3` работает end-to-end
- [ ] `POST /api/yt-dlp` возвращает валидный transcript
- [ ] `POST /api/system-audio/start|stop` захватывает и расшифровывает
- [ ] `/docs` рендерит Swagger UI
- [ ] `.planning/AGENTS.md` содержит autrau-специфику
- [ ] Все коммиты запушены
- [ ] E2E тесты в Obsidian/автотестах проходят
