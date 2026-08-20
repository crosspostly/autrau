# ROADMAP Autrau

План будущих возможностей и улучшений. Пункты отсортированы по приоритету внутри
каждого раздела; статус обновляется по мере реализации. Это «живой» документ —
дополняйте новые идеи в конец списка, помечая приоритет и мотивацию.

## ✅ Сделано в v1.5 (Handi-like UX)

### 🎙 Голосовые заметки + горячая клавиша
- **Статус:** ✅ сделано 2026-08-19
- `Ctrl+Shift+R` (настраивается) → запись микрофона → `data/voice-memos/`. Отдельный
  раздел в UI с табами «📁 Файлы | 🎙 Голосовые заметки». Своя политика авто-очистки
  (7 дней по умолчанию). `MediaRecorder` (Opus 500ms chunks) → ffmpeg → распознавание.
- Endpoints: `POST /api/voice-memos` (list/get/delete), `/api/voice-memos/open-folder`,
  `POST /api/voice/{start,chunk,stop}`. Параметр `_cancel` для отмены без сохранения.

### 🌐 Автоперевод ru→en
- **Статус:** ✅ сделано 2026-08-19
- После каждой расшифровки (если язык ≠ en) автоматически создаётся `<имя>.en.txt`.
  Три провайдера: **LibreTranslate** (public, бесплатно, default), **Argos Translate**
  (локально, ~280 МБ, без облака), **MiniMax** (платно, качество). Можно выбрать в UI
  или в `data/config.json`. В UI показывается badge 🇬🇧 EN рядом с файлом.
- Установка Argos: `pip install argostranslate && argospm install translate-en_ru`.

### 🗑 Bulk-удаление в обоих разделах
- **Статус:** ✅ сделано 2026-08-19
- Чекбокс «Выбрать все» в обеих секциях расшифровок; bulk-кнопка «Удалить выбранные».

### ⚙️ Настройки свернуты за шестерёнкой
- **Статус:** ✅ сделано 2026-08-19
- Секция «3 Настройки» свёрнута по умолчанию; шестерёнка-иконка раскрывает.
  Меньше визуального шума на основном экране.

### 📁 Расширение исходного файла в имени транскрипта
- **Статус:** ✅ сделано 2026-08-19
- `voice-123.mp3` → транскрипт `2026-08-19_voice-123.mp3.txt` (раньше был без `.mp3`).

## ✅ Сделано в v1.5.1 (Argos Translate — локально)

### 🌐 Argos Translate — работает из коробки
- **Статус:** ✅ сделано 2026-08-19
- **Argos Translate** установлен локально (`pip install argostranslate langdetect` +
  модели `translate-en_ru` (187 МБ) + `translate-ru_en` (149 МБ) в
  `~/local/share/argos-translate/packages/`, 336 МБ суммарно).
- Реальный URL моделей: `argos-net.com` (⚠️ НЕ `argosopentech.com` — мёртв с 2024).
  Индекс: `raw.githubusercontent.com/argosopentech/argospm-index/main/`.
- Теперь translation **работает без ключей и без интернета** — `argos` стал preferred
  провайдером (default), `libretranslate` — fallback (его публичные инстансы мёртвы).
- `POST /api/translate/install-argos` — устанавливает пакет + обе модели в фоне.
  В UI: кнопка «📥 Установить Argos» в шестерёнке → «3.5 🌐 Перевод».
- `_translation_startup_check()` логирует ✓/✗ для каждого провайдера при старте.
  В hero появились badges `✓ Argos` / `✓ LibreTranslate` / `🔁 Автоперевод: ВКЛ/выкл`.

### ⚙️ Перевод перенесён ВНУТРЬ шестерёнки
- **Статус:** ✅ сделано 2026-08-19
- Раньше секция «3.5 🌐 Перевод» была отдельной карточкой; теперь это последний
  пункт внутри карточки «3 Настройки». Логика: все настройки — в шестерёнке.

### 🐛 Критические багфиксы
- `tr.translate()` вызывался с параметром `source=...`, которого нет в сигнатуре
  → `502 Ошибка перевода: translate() got an unexpected keyword argument 'source'`.
  Убрано.
- `langdetect` не был в venv → Argos использовал `en→ru` для русского текста → мусор.
  Поставлен + добавлена Cyrillic-эвристика как fallback если `langdetect` отсутствует.
- `ArgosTranslateProvider.is_available()` теперь проверяет наличие обеих моделей
  (раньше только `import argostranslate`) — корректный reason в `/api/translate/providers`.

## Ближайшие (high priority)

### 📤 Экспорт SRT / VTT / JSON
- **Статус:** ✅ сделано 2026-08-19 (v1.5.6)
- Кнопка «📤 Экспорт ▾» в карточке результата → dropdown с SRT/VTT/JSON/TXT.
- Использует `segments` из ответа `/transcribe`; сохраняется в sidecar
  `<stem>.segments.json` рядом с `.txt` (для последующего экспорта без ре-транскрибации).
- Старые расшифровки без sidecar — экспортируются в «плоский» формат
  (один сегмент, равный всему тексту; длительность ~15 символов/сек).
- Endpoint: `GET /api/transcripts/{name}/export?format=srt|vtt|json|txt`.
- Поддерживает русскую кириллицу (UTF-8). SRT использует `,` для миллисекунд,
  VTT — `.` (стандарт W3C).

### 🛠 CLI tool (v1.5.7)
- **Статус:** ✅ сделано 2026-08-20 (v1.5.7)
- `python -m autrau.cli` — subcommands: `transcribe`, `batch`, `providers`, `models`,
  `status`, `health`. Работает через HTTP API сервера, использует urllib (без
  requests). `AUTRAU_API` env var для override URL.
- Пакетная обёртка `autrau/__init__.py` + `__main__.py` + `cli.py` для
  `python -m autrau` (запуск server.py) и `python -m autrau.cli`.

### 🔗 URL → транскрипция через yt-dlp (v1.5.7)
- **Статус:** ✅ сделано 2026-08-20 (v1.5.7)
- YouTube / Vimeo / X / Twitch / SoundCloud / Reddit / ~1500 сайтов.
- `GET /api/yt-dlp/info?url=...` — метаданные (без скачивания).
- `POST /api/yt-dlp {url, language?, provider?, model?}` — SSE: info →
  downloading (0-100%) → transcribing (0-100%) → done.
- `tools/yt_dlp.py` обёртка с FFmpegExtractAudio → WAV. ANSI-коды в ошибках стрипаются.
- Зависимость: `pip install yt-dlp`.

### 🔊 Системный звук / loopback (v1.5.7)
- **Статус:** ✅ сделано 2026-08-20 (v1.5.7)
- Захват того, что играет в колонках/наушниках через `soundcard` (Windows WASAPI
  / macOS BlackHole / Linux PulseAudio monitor).
- `GET /api/system-audio/devices` → список loopback-устройств.
- `POST /api/system-audio/start {device_id}` → запуск (16kHz mono, 100ms чанки).
- `POST /api/system-audio/stop {save_to?}` → SSE: info → done (транскрибированный
  результат). Single-instance lock.
- Зависимость: `pip install soundcard`.

### 🆕 Real self-update (v1.5.8)
- **Статус:** ✅ сделано 2026-08-20 (v1.5.8)
- Persistent state в `data/update_state.json` (atomic write + RLock).
- Endpoints: `GET /api/updates/state`, `POST /api/updates/{check-now,dismiss,apply}`.
- Background scheduler (`_update_scheduler()`) проверяет обновления каждые
  `update_check_interval_hours` (default 6, минимум 1). Если `auto_update_app=true`
  → auto-apply + restart через `os.execv`.
- UI banner `#updateBanner` (gradient teal-blue) с polling каждые 30с.
- 10/10 unit-тестов в `tests/test_update_state.py` покрывают state machine
  (atomic write, should_notify, dismissed reset на новую версию, mark_applied failures).

### 📱 Telegram-бот
- **Статус:** идея · **Оценка:** крупная фича
- Голосовые сообщения (`ogg`/`opus`) и аудиофайлы из чатов → расшифровка через
  существующие провайдеры (faster-whisper / whisper-cpp / parakeet).
- Лимиты: Bot API принимает файлы до **20 МБ** для ботов (50 МБ — через
  `sendDocument` по ссылке для других ботов); длинные голосовые нужно резать на
  куски и склеивать.
- Команды: `/start`, `/transcribe` (reply на голосовое/аудио), `/lang ru|en|auto`,
  `/status`, `/favorites`, `/export srt|vtt|json`.
- Обмен с локальным сервером — через тот же `POST /transcribe`; бот как тонкая
  прослойка.
- Деплой: рядом с сервером (тот же хост), токен — в `.env`/конфиге, без внешних
  зависимостей (python-telegram-bot или aiogram).

### 🖥 Серверный деплой (Linux/systemd)
- **Статус:** идея · **Оценка:** средняя
- systemd-юниты `autrau.service` (веб-сервер) + опциональный `autrau-bot.service`;
  `Restart=always`, логи в journald, автозапуск при загрузке.
- Сейчас сервер рассчитан на локальный запуск (по умолчанию слушает только
  `127.0.0.1`, CORS открыт, аутентификации нет) — для сетевого доступа добавить
  слой защиты (токен/пароль, HTTPS через reverse proxy).
- Готовые скрипты установки и `DEPLOYMENT.md` с инструкцией.

### 🔤 Слово-уровневые таймстампы
- **Статус:** идея · **Оценка:** средняя
- Сегменты с точными таймингами слов (faster-whisper отдаёт `word_timestamps`);
  подложка под экспорт SRT/VTT и редактор.
- В UI — подсветка текущего слова при воспроизведении.

## Среднесрочные (medium priority)

### ⏳ Очередь задач
- **Статус:** идея · **Оценка:** средняя
- Сейчас транскрибация — один синхронный SSE-поток; параллельные запросы
  конкурируют за память (в памяти держится одна модель).
- Очередь: задачи с id, статусами (queued → processing → done/error), прогрессом,
  отменой; UI-список задач с результатами. Фундамент для бота и пакетной загрузки.

### ⛔ Enforce `MAX_UPLOAD_MB`
- **Статус:** ✅ сделано 2026-08-18
- Загрузки больше `MAX_UPLOAD_MB` отклоняются с `413` и понятным сообщением
  в UI (побайтовое чтение, временный файл чистится).

### ▶️ Веб-плеер с волной (для сохранённых расшифровок)
- **Статус:** идея · **Оценка:** средняя
- Привязка расшифровки к исходному аудио (копия в `data/audio/`), клик по
  сегменту → перемотка, подсветка текущей строки. Усиливает ценность избранного.

## Дальние / по запросу (low priority)

### 🍏 macOS
- **Статус:** идея · **Оценка:** средняя
- Проверить/поддержать запуск на macOS (сейчас настройка проверена на Windows):
  `start.command`, пути, whisper-cpp сборка.

### 🌐 Мультиязычный UI
- **Статус:** идея · **Оценка:** средняя
- Переключатель ru/en в шапке, строки в `lang.json`, `Intl` для дат/чисел.
  Отделить тексты от разметки (сейчас — инлайн в `index.html`).

### 🔄 Довести `auto_update_app` до конца
- **Статус:** ✅ сделано 2026-08-20 (v1.5.8)
- Persistent state, background scheduler, UI banner, atomic apply, restart через
  `os.execv`. Подробности — в `docs/API.md` (раздел Self-update) и `docs/ARCHITECTURE.md`.

### 🆕 Portable Windows .exe (v1.6) — в планах
- **Статус:** 💭 идея
- `autrau-desktop/` — Electron + PyInstaller обёртка (см. `C:\obsidian\04_Knowledge\projects\autrau\v1.6-tauri-plan.md`).
- Нативное окно поверх всех приложений, глобальный хоткей (работает вне браузера), system tray.
- System-wide вставка текста (`enigo` или `@nut-tree/nut-js`) вместо browser-only Selection API.
- Dictation indicator как **отдельный webview** (не DOM overlay) — survives при свёрнутом главном окне.
- Решение: **Electron** вместо Tauri (Node уже есть, не нужно 5 ГБ Rust + MSVC).

## Не входит в планы (non-goals)

- Облачный SaaS / публичный хостинг с аккаунтами.
- Распознавание видео с экрана в реальном времени (не голосовые) — только
  аудио/видеофайлы.
- Свои модели ASR «с нуля» — только интеграция существующих провайдеров.

---

Как добавлять: новая фича — кратко (что/зачем/оценка), в соответствующий раздел.
Реализованное — перенести в `CHANGELOG`/коммит и пометить статус «сделано».
