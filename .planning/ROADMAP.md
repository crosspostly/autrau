# Roadmap — Autrau (все версии)

## Overview

| Phase | Name                              | Status      | Version | Est. Time |
|-------|-----------------------------------|-------------|---------|-----------|
| 1     | **Подготовка инфраструктуры**     | ✅ done      | v1.5    | 30 min   |
| 2     | **Горячие клавиши + голосовые**   | ✅ done      | v1.5    | 4-6 hours |
| 3     | **Автоперевод**                   | ✅ done      | v1.5    | 2-3 hours |
| 4     | **Polish + Docs**                 | ✅ done      | v1.5    | 1 hour   |
| 5     | **Vibe-inspired (CLI/yt-dlp/audio/Swagger)** | ✅ done | v1.5.7  | 1.5 hours |
| 6     | **Real auto-update**              | ✅ done      | v1.5.8  | 1 hour   |
| 7     | **Telegram agent bot**            | ✅ done      | v1.7    | 1.5 hours |
| 8     | **Tauri/Electron wrapper (MVP)**  | ✅ done (MVP) | v1.6.0  | 1.5 hours (foundation) |

---

## Phase 1 — Подготовка инфраструктуры ✅ DONE

**Goal:** Закрыть мелкие UX-баги + создать GSD-планирование.

**Tasks:**
- [x] REQ-v1.5-001: Сохранение расширения исходного файла в имени транскрипта
  - File: `tools/cleanup.py::save_transcript`
  - Тест: транскрибировать `voice-123.mp3` → проверить, что в `data/transcripts/` появился `2026-08-19_voice-123.mp3.txt`
- [x] REQ-v1.5-002: Размер в КБ для маленьких файлов
  - File: `tools/cleanup.py::list_transcripts` — добавить `size_kb`
  - File: `index.html::renderTranscripts` — показывать КБ если < 1 МБ
  - Тест: UI показывает `0.5 КБ` для маленьких транскриптов
- [x] GSD-планирование: создать `.planning/` структуру
  - `.planning/PROJECT.md` — описание проекта + текущий milestone
  - `.planning/MILESTONES.md` — история версий
  - `.planning/REQUIREMENTS.md` — детальные требования
  - `.planning/ROADMAP.md` — этот файл
  - `.planning/STATE.md` — текущее состояние
  - `.planning/AGENTS.md` — инструкции для AI-агентов

**Commits:**
- `3d10ebc` — "transcript filename: preserve source extension + show KB if < 1MB"

**Done:** 2026-08-19

---

## Phase 2 — Горячие клавиши + вкладка «Голосовые заметки» 🔄 NEXT

**Goal:** Реал-тайм запись голоса по хоткею + отдельный раздел для таких заметок.

**Sub-phases:**

### 2.1 — Backend: voice-memos API (1.5 hours)

- [ ] `tools/cleanup.py`:
  - `save_voice_memo(text, info)` — аналог `save_transcript`, но в `data/voice-memos/`
  - `list_voice_memos()` — аналог `list_transcripts`
  - `run_voice_cleanup(days)` — отдельный cleanup
- [ ] `server.py`:
  - `POST /api/voice/start` → создаёт сессию с id
  - `POST /api/voice/chunk` (multipart `audio/webm`) → добавляет в сессию
  - `POST /api/voice/stop` → склеивает чанки, транскрибирует, сохраняет
  - `GET /api/voice/live/{id}` → последний partial (опционально)
  - `GET /api/transcripts?category=voice-memos|files|all` — фильтр

### 2.2 — Frontend: MediaRecorder + hotkey (2-3 hours)

- [ ] `index.html`:
  - Hotkey config: чекбокс + input для настройки (`<input>` ловит keydown, отображает "Ctrl+Shift+R")
  - Default: `Ctrl+Shift+R` (или `Alt+R` для совместимости)
  - On hotkey match → toggle recording
  - On record start: floating overlay с pulse-точкой + таймером + live-текстом
  - `navigator.mediaDevices.getUserMedia({audio: true})` — захват
  - `MediaRecorder` → `audio/webm;codecs=opus` (или PCM сборка → wav)
  - Каждые 500ms POST чанк на `/api/voice/chunk`
  - Polling `/api/voice/live/{id}` для partial-транскрипции (если есть)
  - On stop: `POST /api/voice/stop`, показать результат, обновить список voice-memos
  - `beforeunload` → `navigator.sendBeacon('/api/voice/stop')` для graceful shutdown

### 2.3 — UI: табы в секции «Расшифровки» (1 hour)

- [ ] `index.html`:
  - Два таба: «📁 Файлы» (default) | «🎙 Голосовые заметки»
  - Активный таб подсвечивается (CSS)
  - Контент перерисовывается по табу
  - Empty state для voice-memos: «Нажмите Ctrl+Shift+R для записи голосовой заметки»
  - «Открыть папку» → открывает соответствующую папку

### 2.4 — Config: hotkey + voice-memo dir (15 min)

- [ ] `tools/config.py`:
  - `hotkey: "Ctrl+Shift+R"` (default)
  - `voice_memo_dir: "data/voice-memos/"`
  - `voice_memo_cleanup_after_days: 7`

**Tests:**
- [ ] Юнит: `save_voice_memo` сохраняет в правильную папку
- [ ] API: `/api/voice/start` → id, `/api/voice/stop` → file в `data/voice-memos/`
- [ ] UI: hotkey нажат → overlay появился → запись → стоп → файл в списке
- [ ] UI: переключение табов работает, bulk selection не ломается
- [ ] Graceful: закрытие вкладки во время записи → файл всё равно сохраняется

**Commit strategy:** один большой коммит "phase 2: hotkey + voice memos" с подробным message, или 4 маленьких (2.1 / 2.2 / 2.3 / 2.4). Рекомендую 4 коммита — проще откатить.

---

## Phase 3 — Автоперевод ru→en 🔄 PENDING

**Goal:** Опциональный автоматический перевод расшифровок на английский.

**Sub-phases:**

### 3.1 — Translation provider abstraction (1 hour)

- [ ] `tools/translation.py` (новый файл):
  - `TranslationProvider` (base, как `Provider` в providers/)
  - `LibreTranslateProvider` (HTTP к libretranslate.com или local)
  - `MiniMaxProvider` (через openai-совместимый API)
  - Реестр + `get_provider(name) → instance`

### 3.2 — Server: translate endpoint + post-transcription hook (1 hour)

- [ ] `server.py`:
  - `POST /api/translate` → `{text, source, target}` → `{translated, provider}`
  - В `transcribe` после `save_transcript` → если `cfg.translate_to_en` и `info.language != "en"`:
    - `translated = translate(out["text"], "auto", "en")`
    - `save_translated(...)` → пишет `*.en.txt` рядом
  - `GET /api/translate/providers` → список доступных провайдеров + статус

### 3.3 — UI: галочка + badge (30 min)

- [ ] `index.html`:
  - В секции «3 НАСТРОЙКИ» — чекбокс «Автоматически переводить на английский»
  - При наличии `.en.txt` — badge `🇬🇧 EN` рядом с именем файла
  - Клик на badge → открывает переведённую версию

**Tests:**
- [ ] Юнит: `translate("Привет мир", "ru", "en")` → "Hello world" (или похожее)
- [ ] API: `/api/translate` round-trip работает
- [ ] E2E: включил чекбокс → транскрибировал русское аудио → появилось `*.en.txt`
- [ ] Edge: перевод упал → оригинал на месте, в логе warning

**Estimated:** 2-3 hours.

---

## Phase 4 — Polish + Docs 🔄 PENDING

**Goal:** CI green, docs обновлены, README рассказывает про новые фичи.

**Tasks:**
- [ ] `docs/ROADMAP.md` — обновить статус (v1.5 done)
- [ ] `docs/CONFIGURATION.md` — добавить `hotkey`, `translate_to_en`, `voice_memo_*`
- [ ] `README.md` — секция «Voice memos & translation» с GIF/скриншотом
- [ ] CI: убедиться, что новые тесты проходят
- [ ] Memory note в `MEMORY.md`: «v1.5 shipped: hotkey, voice memos, translation»
- [ ] Obsidian note `04_Knowledge/projects/autrau/v1.5-handi-ux.md` (если принято workflow)

**Estimated:** 1 hour.

---

## Risks & Open Questions

### Voice-memos без потоковой транскрипции (v1.5)

Без WebSocket + VAD финальный текст появляется только ПОСЛЕ стопа записи. Юзеру придётся ждать N секунд после отпускания хоткея. Можно улучшить в v1.5.1:

- VAD-чанк каждые 3 сек → partial → UI
- Или хотя бы "индикатор обработки" пока идёт финальная транскрипция

### Hotkey в браузере vs глобальный

В браузере хоткей работает **только когда вкладка в фокусе**. Если юзер переключился в другое приложение — не сработает. Для глобального хоткея нужен Electron/Tauri (см. v1.6 portable exe).

Workaround для v1.5: floating overlay делает окно более "живым" + tab-focus reminder. Но это не идеал.

### Translation provider на AMD

LibreTranslate публичный может быть медленным. MiniMax платный. NLLB-200 локально — 600MB модель, может не поместиться. Нужно явно спросить юзера, какой провайдер подключить.

---

# Next milestone — v1.5.7+ (vibe-inspired)

**Анализ:** `C:\obsidian\04_Knowledge\wiki\open-source-vibe-analysis.md`
**Контекст:** Vibe (thewh1teagle, 7.1k⭐) — Tauri-shell + sona-раннер для офлайн-транскрибации.
Изучили архитектуру, выделили 5 быстрых побед и 3 средних проекта для autrau.

## Phase 5 — Vibe-inspired quick wins (v1.5.7) 🔄 NEXT

**Goal:** Перенять низко висящие плоды из vibe: CLI tool, yt-dlp, system audio, Swagger UI.
Не трогает core, не ломает API. Каждая фича — отдельный коммит.

### 5.1 — CLI tool `python -m autrau.cli` (45 min)

Использование autrau из терминала и скриптов:
- `python -m autrau.cli transcribe file.mp3 --language ru --output out.txt`
- `python -m autrau.cli providers` — список провайдеров
- `python -m autrau.cli batch dir/` — пакетная обработка

**Files:** `tools/cli.py` (новый), `setup.py`/`pyproject.toml` (entry point)
**REQ:** REQ-v1.5.7-001

### 5.2 — yt-dlp endpoint `POST /api/yt-dlp?url=...` (1 hour)

Скачать аудио по URL → транскрибировать:
- `POST /api/yt-dlp` body `{url, language?, model?}` → скачивает, транскрибирует, возвращает результат
- `GET /api/yt-dlp/info?url=...` → title, duration, thumbnail (UI preview)
- UI: новая кнопка «🔗 Из URL» рядом с «📁 Файл»

**Files:** `server.py` (endpoint), `tools/yt_dlp.py` (helper), `index.html` (UI)
**Dep:** `yt-dlp` (~10 МБ)
**REQ:** REQ-v1.5.7-002

### 5.3 — System audio loopback (Windows WASAPI) (2 hours)

Расшифровка того что играет в колонках (YouTube/Zoom/etc):
- `POST /api/system-audio/start` → начинает захват системного звука
- `POST /api/system-audio/stop` → стоп, транскрибировать
- Использует `soundcard` (PyPI) или `pyaudiowpatch` для Windows WASAPI loopback

**Files:** `tools/system_audio.py` (новый), `server.py` (endpoints)
**Note:** Windows only initially, macOS/Linux в v1.6+
**REQ:** REQ-v1.5.7-003

### 5.4 — Swagger UI `/docs` (10 min)

FastAPI уже включает Swagger из коробки. Просто проверить что `/docs` работает.
**Files:** `server.py` (проверить, что app определён через `FastAPI()`, не `__call__`)
**REQ:** REQ-v1.5.7-004

### 5.5 — AGENTS.md update (30 min)

Скопировать паттерн из vibe + добавить autrau-специфичное:
- uv для скриптов (PEP 723)
- plans/<name>/<name>_NNN.py для валидации
- pnpm-аналог (autrau не использует)

**Files:** `.planning/AGENTS.md`
**REQ:** REQ-v1.5.7-005

**Estimated:** 4-5 hours total.

---

## Phase 6 — Real auto-update (v1.5.8) ✅ DONE (2026-08-20)

**Goal:** Реальный auto-update с persistent state, background scheduler, UI banner.

**Sub-phases:**
- 6.1 — `tools/update_state.py` (NEW) — persistent state в `data/update_state.json` (atomic writes, thread-safe) ✅
- 6.2 — `tools/update.py` — добавлены `current_version()`, `latest_version()` ✅
- 6.3 — server: 4 новых endpoint'а + `_update_scheduler()` background task + `_os.execv` restart ✅
- 6.4 — UI: `#updateBanner` (gradient), polling каждые 30s, Apply с restart watcher ✅
- 6.5 — Settings: `auto_update_app` checkbox + `update_check_interval_hours` input ✅
- 6.6 — Tests: 10/10 unit тестов в `tests/test_update_state.py` ✅
- 6.7 — Docs: docs/API.md + docs/CONFIGURATION.md ✅

**New endpoints:**
- `GET /api/updates/state` — persistent state + should_notify + auto_update_enabled
- `POST /api/updates/check-now` — force check (обновляет state)
- `POST /api/updates/dismiss` — mark dismissed for current latest_version
- `POST /api/updates/apply` — git pull + pip upgrade; restart если auto_update_app=true

**Механика:**
- `auto_update_app=false` (default): юзер видит баннер в UI → жмёт «Обновить» → server применяет → UI polling ждёт /health → reload
- `auto_update_app=true`: background scheduler (каждые N часов) → если available, apply + restart через `os.execv` (через 2с delay)
- Single instance lock — concurrent apply невозможен
- State persistent в `data/update_state.json` (atomic write, RLock)
- `should_notify()` учитывает `dismissed_version` — banner не показывается повторно до новой версии

**E2E проверено:** apply 9.3s (no-op, current==latest), state корректно обновляется (last_apply_at, result, version, available→false).

---

## Phase 7 — Telegram agent bot (v1.7) ✅ DONE (2026-08-20)

**Goal:** Agent-бот в Telegram для usability/QA. Голосовые и аудио из чата
→ авто-расшифровка. Команды `/status`, `/providers`, `/check`, `/update`, `/ask`.
Whitelist chat_id по умолчанию (безопасный дефолт).

**Status:** ✅ shipped. Plan: `.planning/phases/7-telegram-bot/PLAN.md`.

**Стек:** `python-telegram-bot` v21.11.1 (async, polling mode). Бот — отдельный
процесс, общается с autrau-server через HTTP API.

**Sub-phases (7.1–7.7):** scaffold, whitelist, 11 команд, voice/audio handlers,
agent mode (9 FAQ patterns), 19/19 tests, docs + UI.

**Estimated actual:** 1.5 hours (включая тесты, docs, UI).

---

## Phase 8 — Tauri/Electron wrapper (v1.6) 🔄 v1.6.0 SHIPPED (MVP, 2026-08-20)

**Goal:** Portable Windows .exe через Electron (Tauri отклонён — 5GB Rust toolchain
ради 5-10MB savings нерентабельно). Используем паттерн vibe:
- `autrau-desktop/` (Electron + PyInstaller sidecar) — **отдельный репо** `crosspostly/autrau-desktop`
- System tray + global hotkey `Alt+R` + frameless window
- Real global hotkey (работает вне браузера)
- Dev mode: спавнит Python venv из `../autrau`
- Prod mode: спавнит PyInstaller-bundled `autrau-server.exe` из `resources/`

**Status:** v1.6.0 MVP shipped (commit `e50c310` на https://github.com/crosspostly/autrau-desktop).
Полный план в Obsidian; v1.6.1 (PyInstaller sidecar) и v1.6.2 (polish + GitHub Actions) — следующие.

**См.:** `C:\obsidian\04_Knowledge\projects\autrau\v1.6-tauri-plan.md`
**См.:** `C:\Users\varsm\OneDrive\Desktop\projects\autrau-desktop\README.md`

---

*Last updated: 2026-08-20 13:30 — Phase 7 (Telegram bot) added, Phase 8 (Tauri→Electron) renumbered*
