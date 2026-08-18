# Roadmap — v1.5 (Handi-like UX)

## Overview

| Phase | Name                              | Status      | REQ-IDs                  | Est. Time |
|-------|-----------------------------------|-------------|--------------------------|-----------|
| 1     | **Подготовка инфраструктуры**     | ✅ done      | REQ-v1.5-001, REQ-v1.5-002 | 30 min   |
| 2     | **Горячие клавиши + голосовые**   | 🔄 next     | REQ-v1.5-003, REQ-v1.5-005 | 4-6 hours |
| 3     | **Автоперевод**                   | 🔄 pending  | REQ-v1.5-004              | 2-3 hours |
| 4     | **Polish + Docs**                 | 🔄 pending  | -                         | 1 hour   |

**Total estimated:** 8-10 hours.

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

*Last updated: 2026-08-19*
