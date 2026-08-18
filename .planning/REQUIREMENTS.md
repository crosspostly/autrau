# Requirements — v1.5 (Handi-like UX)

## Validated (shipped)

### REQ-v1.5-001: Расширение исходного файла в имени транскрипта ✅

**Описание:** В имени сохраняемого `.txt` файла должно сохраняться расширение исходного аудио/видео файла. Источник `voice-123.mp3` → транскрипт `2026-08-18_voice-123.mp3.txt` (а не `2026-08-18_voice-123.txt`).

**Мотивация:** При просмотре папки `data/transcripts/` сразу видно, откуда транскрипт. Без расширения непонятно, что за источник был.

**Acceptance:**
- [x] `tools/cleanup.py::save_transcript` сохраняет `src_suffix` (`.mp3`, `.wav`, `.m4a`, ...) в имени
- [x] При коллизии имён добавляется `_N` перед `src_suffix`
- [x] Расширение `.txt` остаётся (транскрипт всегда `.txt`)

**Validation:** committed `3d10ebc`, server restart confirmed.

---

### REQ-v1.5-002: Размер в КБ для маленьких файлов ✅

**Описание:** Если `size_mb < 1`, показывать размер в КБ (`0.5 КБ` вместо `0.0 МБ`).

**Мотивация:** Транскрипты коротких аудио (голосовые 5-10 сек) — килобайтные файлы. `0.0 МБ` — неинформативно, юзер не понимает, пустой ли файл.

**Acceptance:**
- [x] `tools/cleanup.py::list_transcripts` возвращает `size_kb` (округлено до 1 знака)
- [x] `index.html::renderTranscripts` показывает `${size_kb} КБ` если `size_mb < 1`, иначе `${size_mb} МБ`
- [x] Никаких регрессий для больших файлов (всё ещё МБ)

**Validation:** committed `3d10ebc`, UI inspected in browser.

---

## Active (в работе / в плане)

### REQ-v1.5-003: Горячие клавиши для реал-тайм записи (Handi-style) 🔄

**Описание:** Настраиваемое сочетание клавиш для активации записи с микрофона прямо из браузера. По нажатию — floating overlay с индикатором записи и live-транскрипцией. По повторному нажатию (или Esc) — стоп записи, финальная расшифровка сохраняется в `data/voice-memos/`.

**Мотивация:** Как в Handi.app — нажал Ctrl+Shift+R, говоришь, текст появляется в реальном времени, не нужно загружать файл. Главный UX-win для тех, кто делает заметки голосом.

**Архитектура:**

```
┌─────────────────┐    POST /api/voice/start     ┌──────────────────┐
│  Browser         │  ──────────────────────────>  │  FastAPI         │
│                  │  <─── 200 (recording id)       │                  │
│ navigator.media  │                                │  Recv audio      │
│  Devices.getUser │  POST /api/voice/chunk         │  chunks, buffer  │
│  MediaStream     │  (multipart audio/wav)         │  in memory       │
│ MediaRecorder    │  ──────────────────────────>   │                  │
│                  │  <─── 200 (chunk received)     │                  │
│                  │                                │                  │
│ (recording...)   │  POST /api/voice/stop          │  Concatenate →  │
│                  │  ──────────────────────────>   │  transcribe      │
│                  │  <─── 200 {text, file}         │  full audio      │
└─────────────────┘                                 └──────────────────┘
```

**Опционально v2:** streaming через WebSocket → server-side VAD → live partials.

**Тех. детали:**

- **Frontend (index.html):**
  - `navigator.mediaDevices.getUserMedia({ audio: true })` — захват микрофона
  - `MediaRecorder` → кодирование в `audio/webm;codecs=opus` (или wav через PCM-сборку, чтобы сервер не конвертировал)
  - Каждые 250-500 ms POST чанк на `/api/voice/chunk`
  - Floating overlay: pulse-точка + таймер + live-текст (через polling `/api/voice/live/{id}` раз в 500ms)
  - Настройка хоткея: `<input>` + `keydown` listener → сохраняет в `cfg.hotkey = "Ctrl+Shift+R"`, восстанавливает при загрузке
  - On `keydown` matching hotkey → toggle recording
  - Перед стартом записи: запросить permission на микрофон (один раз)
  
- **Backend (server.py):**
  - `POST /api/voice/start` → создаёт in-memory сессию `{id, chunks: [], started_at, last_partial: ""}`
  - `POST /api/voice/chunk` → добавляет байты в сессию, опционально прогоняет через partial transcription (lazy VAD)
  - `POST /api/voice/stop` → склеивает чанки, прогоняет через `p.transcribe(full_audio)`, сохраняет в `data/voice-memos/`, возвращает `{text, file_path}`
  - `GET /api/voice/live/{id}` → возвращает последний partial (если VAD/transcription потоковый)
  - `audio/voice-memos/` — отдельная gitignored-папка (не в `data/transcripts/`, чтобы не мешать auto-cleanup)
  - `tools/cleanup.py::save_voice_memo(name, text, info)` — аналог `save_transcript`, но с `category=voice-memo` в заголовке

- **Config (data/config.json + tools/config.py):**
  - `hotkey: "Ctrl+Shift+R"` (default)
  - `voice_memo_cleanup_after_days: 7` (отдельный лимит)
  - `voice_memo_dir: "data/voice-memos/"` (можно поменять)

- **Edge cases:**
  - Микрофон не разрешён → показать понятную ошибку "нажмите 🔒 в адресной строке → разрешите микрофон"
  - Запись больше 10 мин → автоматический стоп + предупреждение
  - Другой процесс уже использует микрофон → graceful error
  - Юзер переключил вкладку — `MediaRecorder` продолжает работать (Chrome/Firefox), стрим не обрывается
  - Юзер закрыл вкладку — `beforeunload` → `navigator.sendBeacon('/api/voice/stop')` для сохранения

**Acceptance:**
- [ ] Настраиваемый хоткей в UI (по умолчанию `Ctrl+Shift+R`)
- [ ] По нажатию хоткея — overlay с индикатором записи (красная пульсирующая точка + таймер)
- [ ] Микрофон пишется в реальном времени, чанки уходят на сервер каждые 500ms
- [ ] Live-транскрипция (если потоковая) или хотя бы финальный текст по стоп
- [ ] По стопу — текст сохраняется в `data/voice-memos/` + появляется во вкладке «Голосовые»
- [ ] Хоткей работает только когда фокус на странице autrau (не перехватываем глобально — для этого нужен Electron/Tauri)
- [ ] Esc во время записи → стоп

**Out of scope (v1.5):**
- Глобальные хоткеи вне браузера (требует native wrapper — v2)
- Потоковая live-транскрипция чанков (требует VAD + streaming через WebSocket — v2)
- VAD (voice activity detection) для пропуска тишины (v2)

**Estimated:** 4-6 часов.

---

### REQ-v1.5-004: Автоперевод ru→en после расшифровки 🔄

**Описание:** В настройках — галочка «Автоматически переводить на английский». Если включено — после каждой успешной транскрипции (или voice memo) сервер прогоняет текст через переводчик и сохраняет `.en.txt` рядом (или заменяет основной `.txt` — на выбор юзера).

**Мотивация:** Юзер часто слушает англоязычные подкасты/видео. Сейчас транскрипт приходит на языке оригинала, переключать язык в настройках каждый раз неудобно.

**Тех. детали:**

- **Backend:**
  - Новый endpoint `POST /api/translate` — `{text, source="auto", target="en"}` → `{translated, provider, model}`
  - Провайдеры перевода (по приоритету):
    1. **LibreTranslate** (если локально или публичный инстанс доступен) — бесплатно
    2. **MiniMax API** (как fallback, платный) — для high-quality перевода
    3. **Локальная модель** (NLLB-200-distilled-600M, ONNX, ~600MB) — opt-in в настройках
  - Если ни один провайдер не сконфигурирован — translation step пропускается, в лог пишется warning, юзер видит "перевод недоступен"
  - `server.py::transcribe` после `clean.save_transcript(...)` → если `cfg.translate_to_en` → `translate(text)` → `save_translated(..., .en.txt)`

- **Config (data/config.json + tools/config.py):**
  - `translate_to_en: false` (default, opt-in)
  - `translation_provider: "libretranslate" | "minimax" | "local-nllb"`
  - `libretranslate_url: ""` (пустой = пытаемся public, иначе локальный)
  - `minimax_api_key: ""` (из `auth.json` если есть)

- **Frontend (index.html):**
  - В настройках (секция «3 НАСТРОЙКИ» или новый раздел «Перевод»): чекбокс «Автоматически переводить на английский»
  - Сохранение в `cfg.translate_to_en`
  - При наличии `.en.txt` — в списке расшифровок отображается "🇬🇧 EN" badge

- **Edge cases:**
  - Транскрипт уже на английском → не переводим (детект через lang detection на тексте, или через `info.language` от провайдера)
  - Перевод не удался → оригинальный файл остаётся, в лог warning, юзеру ничего не показываем
  - Параллельные транскрипции → перевод тоже параллельный, но каждая пишет в свой файл (без race)

**Acceptance:**
- [ ] Чекбокс в UI: `cfg.translate_to_en`
- [ ] При включённой опции — после каждой транскрипции создаётся `.en.txt` рядом
- [ ] Поддержка хотя бы одного провайдера перевода (LibreTranslate или MiniMax)
- [ ] Если перевод упал — оригинал сохранён, ошибка в логе
- [ ] Badge в UI: «🇬🇧 EN» если есть `.en.txt`

**Out of scope (v1.5):**
- Перевод на языки кроме en (v2)
- Редактирование перевода в UI
- Streaming translation для voice-memos (v2)

**Estimated:** 2-3 часа (без локальной модели, с LibreTranslate или MiniMax).

---

### REQ-v1.5-005: Вкладка «Голосовые заметки» в расшифровках 🔄

**Описание:** Отдельный таб в секции «4 РАСШИФРОВКИ» — «Голосовые заметки». Содержит только файлы из `data/voice-memos/` (то, что записано хоткеем). Всё остальное — в табе «Файлы» (по умолчанию).

**Мотивация:** Голосовые заметки имеют другую семантику: они короче, чаще создаются, имеют другие потребности (быстрый доступ, копирование). Смешивать с «большими» расшифровками длинных видео — неудобно.

**Тех. детали:**

- **Backend:**
  - `GET /api/transcripts?category=voice-memos` — фильтр по категории
  - `GET /api/transcripts?category=all` (default) — все файлы
  - `tools/cleanup.py::list_voice_memos()` — аналог `list_transcripts`, но сканирует `data/voice-memos/`
  - `data/voice-memos/` — gitignored, новая папка
  - Favorites работают и для voice-memos (отдельный файл `data/favorites_voice.json` или общий `favorites.json` с префиксом категории)

- **Frontend (index.html):**
  - В секции «4 РАСШИФРОВКИ» — две таб-кнопки: «📁 Файлы» (default) | «🎙 Голосовые заметки»
  - Активный таб подсвечивается, контент перерисовывается
  - На табе «Голосовые» — список из `data/voice-memos/`, тот же UI что и для файлов
  - Bulk selection (чекбокс "Выбрать все") работает в обеих вкладках независимо
  - "Открыть папку" открывает соответствующую папку (`data/transcripts/` или `data/voice-memos/`)

- **Edge cases:**
  - Папка `data/voice-memos/` не существует → показать "Пока нет голосовых заметок — нажмите Ctrl+Shift+R чтобы записать"
  - Миграция: если у юзера уже есть файлы в `data/transcripts/` с префиксом `voice-` (старые) → оставляем как есть, новая категория только для НОВЫХ
  - Auto-cleanup: отдельный `voice_memo_cleanup_after_days` (default 7 дней)

**Acceptance:**
- [ ] Два таба: «Файлы» (default) и «Голосовые заметки»
- [ ] При пустой папке voice-memos — понятный empty state с подсказкой про хоткей
- [ ] Bulk selection работает в обеих вкладках
- [ ] Кнопка "Открыть папку" ведёт в правильную папку для активного таба
- [ ] Favorites работают независимо (можно ⭐ отдельно voice-memo и отдельно файл)

**Out of scope (v1.5):**
- Полнотекстовый поиск по всем расшифровкам (v2)
- Экспорт в Notion/Obsidian (отдельная фича)
- Теги/проекты для группировки (v2)

**Estimated:** 1-2 часа (после REQ-v1.5-003, потому что нужна папка voice-memos + endpoint).

---

## Out of Scope (текущий milestone)

- **Portable exe** (PyInstaller, Handy-style "1 exe, всё внутри") — отдельный крупный проект, v1.6
- **iOS / Android client** — нет
- **Sync между устройствами** — нет
- **Speaker diarization** (кто говорит) — v2
- **Потоковая live-транскрипция** для voice-memos — v2 (WebSocket + VAD)
- **Полнотекстовый поиск** по расшифровкам — v2
- **Экспорт в Notion/Obsidian** — отдельная фича

---

*Last updated: 2026-08-19*
