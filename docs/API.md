<!-- generated-by: gsd-doc-writer -->
# HTTP API Autrau

Базовый URL: `http://127.0.0.1:8000` (по умолчанию; настраивается через `AUTRAU_HOST`/`AUTRAU_PORT`).

## Аутентификация

Аутентификации нет. Приложение рассчитано на локальный запуск и по умолчанию слушает только `127.0.0.1`. CORS открыт (`allow_origins=["*"]`) — не выставляйте сервер в интернет без защиты.

## Обзор эндпоинтов

### Системные

| Метод | Путь | Описание |
|---|---|---|
| `GET` | `/` | Web UI (HTML) |
| `GET` | `/docs` | Swagger UI (auto-generated OpenAPI) |
| `GET` | `/openapi.json` | OpenAPI schema (JSON) |
| `GET` | `/health` | Статус сервера, версия, загруженная модель |

### Провайдеры и модели

| Метод | Путь | Описание |
|---|---|---|
| `GET` | `/api/providers` | Провайдеры, их модели, статус установки, активный выбор |
| `GET` | `/api/config` | Текущая конфигурация (JSON) |
| `POST` | `/api/config` | Обновить ключи конфигурации |
| `POST` | `/api/provider/load` | Загрузить провайдера+модель в память |
| `POST` | `/api/provider/install` | Установить провайдер через pip |
| `POST` | `/api/model/download` | Скачать модель (SSE-прогресс) |
| `GET` | `/api/model/check?provider=...&model=...` | Проверить обновление одной модели |

### Транскрибация

| Метод | Путь | Описание |
|---|---|---|
| `POST` | `/transcribe` | Транскрибация аудио (multipart, SSE-поток) |

### Расшифровки и голосовые заметки

| Метод | Путь | Описание |
|---|---|---|
| `GET` | `/api/transcripts` | Список расшифровок + флаги избранного + наличие `.en.txt` |
| `GET` | `/api/transcripts/{name}` | Скачать/открыть один `.txt` |
| `GET` | `/api/transcripts/{name}/export?format=...` | Экспорт в SRT / VTT / JSON / TXT (v1.5.6) |
| `DELETE` | `/api/transcripts` | Удалить выбранные расшифровки (body: `{"names": [...]}`) |
| `POST` | `/api/transcripts/open-folder` | Открыть папку `data/transcripts/` в проводнике |
| `POST` | `/api/favorites` | Пометить/снять избранное (защита от авто-очистки) |
| `GET` | `/api/voice-memos` | Список голосовых заметок + наличие `.en.txt` |
| `GET` | `/api/voice-memos/{name}` | Скачать одну голосовую заметку |
| `DELETE` | `/api/voice-memos` | Удалить выбранные голосовые заметки |
| `POST` | `/api/voice-memos/open-folder` | Открыть папку `data/voice-memos/` в проводнике |
| `POST` | `/api/voice/start` | Начать сессию записи (возвращает `id`) |
| `POST` | `/api/voice/chunk` | Добавить аудио-чанк (multipart, `id` + `chunk`) |
| `POST` | `/api/voice/stop` | Финализировать сессию: склейка → транскрипция → сохранение в voice-memos |
| `POST` | `/api/cleanup` | Удалить расшифровки старше N дней |

### Перевод (v1.5 / v1.5.1)

| Метод | Путь | Описание |
|---|---|---|
| `POST` | `/api/translate` | Перевести текст (body: `{text, target?, provider?, fallback?}`) |
| `GET` | `/api/translate/providers` | Какие провайдеры перевода доступны прямо сейчас |
| `POST` | `/api/translate/install-argos` | Установить `argostranslate`+`langdetect`+обе модели en_ru/ru_en в фоне |

### URL → транскрипция (v1.5.7)

| Метод | Путь | Описание |
|---|---|---|
| `GET` | `/api/yt-dlp/info?url=...` | Метаданные видео (title, duration, thumbnail) — без скачивания |
| `POST` | `/api/yt-dlp` | Скачать аудио через yt-dlp + транскрибировать (SSE) |

### Системный звук / loopback (v1.5.7)

| Метод | Путь | Описание |
|---|---|---|
| `GET` | `/api/system-audio/devices` | Список loopback-устройств |
| `POST` | `/api/system-audio/start` | Начать запись системного звука |
| `POST` | `/api/system-audio/stop` | Остановить запись + транскрибировать (SSE) |

### Обновления (v1.5.8)

| Метод | Путь | Описание |
|---|---|---|
| `GET` | `/api/updates` | Проверка обновлений (JSON; `?stream=1` — SSE-прогресс). Legacy. |
| `POST` | `/api/updates/app` | Self-update (DEPRECATED → use `/api/updates/apply`) |
| `GET` | `/api/updates/state` | Persistent state: `current/latest/available/should_notify/auto_update_enabled` |
| `POST` | `/api/updates/check-now` | Force check: обновляет state без auto-apply |
| `POST` | `/api/updates/dismiss` | Dismiss banner для текущей `latest_version` |
| `POST` | `/api/updates/apply` | Apply update: git pull + pip upgrade. Если `auto_update_app=true` → restart через `os.execv` |

## Форматы запросов и ответов

### JSON-эндпоинты

Все эндпоинты, кроме помеченных SSE, отвечают `application/json`.

`GET /health`:

```json
{
  "status": "ok",
  "version": "1.0.0",
  "python_ok": true,
  "loaded": { "provider": "faster-whisper", "model": "small", "device": "cpu" }
}
```

`GET /api/providers` — массив провайдеров: `name`, `display_name`, `description`, `requires_gpu`, `installed`, `reason`, `install_hint`, `default_model`, `models` (с `size_mb`, `downloaded`, `source_url`, `languages`, `russian` — флаг «поддерживает русский»), `languages`, `homepage` + блок `active` с текущим выбором.

`POST /api/config` — тело — произвольный набор ключей из конфигурации; обновляются только известные ключи (см. [CONFIGURATION.md](CONFIGURATION.md)):

```json
{ "language": "en", "cleanup_after_days": 30 }
```

Ответ — полная конфигурация после применения.

`POST /api/cleanup` — тело опционально: `{"days": N}` переопределяет значение из конфига для одного запуска; без тела используется `cleanup_after_days`. Расшифровки из избранного никогда не удаляются, даже если подходят по возрасту (считаются в `protected`):

```json
{ "ok": true, "enabled": true, "days": 1, "deleted": 2, "protected": 1, "kept": 1, "freed_mb": 0.01, "active": true }
```

`GET /api/transcripts` — список сохранённых расшифровок с метаданными и флагом избранного. Мёртвые записи избранного (файл удалён) вычищаются автоматически:

```json
{
  "transcripts": [
    { "name": "2026-08-17_10-00-00_речь.txt", "size_bytes": 1240, "size_mb": 0.0, "modified": "2026-08-17T10:00:03", "is_favorite": true }
  ],
  "count": 1
}
```

`POST /api/favorites` — тело `{"name": "файл.txt"}` переключает (toggle) состояние; `{"name": "файл.txt", "favorite": true|false}` задаёт явно. Избранные расшифровки защищены от авто-очистки (`run_cleanup` пропускает их до проверки возраста); снятие ярлыка снова делает файл кандидатом на удаление при следующем прогоне. `404`, если файл не существует. Ответ — `{"name": "...", "is_favorite": true|false}`.

### Voice memos (v1.5)

`GET /api/voice-memos` — список голосовых заметок из `data/voice-memos/` с теми же полями что и `/api/transcripts` + `has_translation` (есть ли `<имя>.en.txt`) и `translation_name`.

`GET /api/voice-memos/{name}` — отдать один `.txt`. `404` если нет.

`DELETE /api/voice-memos` — body: `{"names": [...]}`. Имена sanitized через `Path.name`. Ответ: `{"ok": true, "deleted": [...], "missing": [...]}`.

`POST /api/voice-memos/open-folder` — открыть `data/voice-memos/` в проводнике.

`POST /api/voice/start` — создать сессию записи. Ответ: `{"id": "...", "started_at": "ISO"}`. `id` живёт до стопа/перезагрузки.

`POST /api/voice/chunk` — multipart: `id` (form field) + `chunk` (file, `audio/webm`). На каждый чанк возвращает `{"id", "received_bytes", "total_chunks"}`. `404` если id не найден.

`POST /api/voice/stop` — body: `{"id": "...", "language": "ru"}` (опционально). Склеивает все чанки сессии → конвертирует через ffmpeg (если нужно) → транскрибирует активным провайдером → сохраняет в `data/voice-memos/<timestamp>.txt`. Если включён `translate_to_en` — создаёт `<timestamp>.en.txt`. Ответ: `{"id", "text", "file", "dir"}`. Параметр `_cancel: true` — сессия дропается без транскрипции (используется при отмене записи).

### Translation (v1.5 / v1.5.1)

`POST /api/translate` — body: `{"text": "...", "target": "en", "provider": "argos" | "libretranslate" | "minimax", "fallback": "..."}`. Поля `provider`/`fallback`/`libretranslate_url`/`libretranslate_key`/`minimax_key` опциональны — берутся из `data/config.json` если не указаны. Источник языка определяется автоматически (`langdetect` + Cyrillic-эвристика для Argos; `source=auto` для LibreTranslate). Ответ: `{"translated": "...", "provider": "argos", "target": "en"}`. `502` если все провайдеры недоступны.

`GET /api/translate/providers` — статус каждого провайдера: `{"providers": [{"name", "available", "reason"}, ...], "translate_to_en": bool}`. Удобно для UI: показывает какие провайдеры реально работают, обновляет badge'ы в hero. Вызов с таймаутом 5с на провайдер (is_available может зависнуть).

`POST /api/translate/install-argos` — устанавливает локальный движок Argos:
- pip install `argostranslate` + `langdetect` (если не установлены)
- Обновляет индекс пакетов с GitHub (`raw.githubusercontent.com/argosopentech/argospm-index/main/`)
- Скачивает обе модели в фоне: `translate-en_ru` (187 МБ) + `translate-ru_en` (149 МБ) → `~/local/share/argos-translate/packages/`
- Ответ сразу: `{"ok": true, "started": true, "installing": ["translate-en_ru", "translate-ru_en"], "note": "..."}`. Установка идёт в фоне; опрашивать `/api/translate/providers` пока `argos.available=true`.
- Если модели уже стоят — `{"ok": true, "already_installed": true}`.

### URL → транскрипция (v1.5.7)

`GET /api/yt-dlp/info?url=<URL>` — `{"title", "duration" (sec), "thumbnail", "uploader", "webpage_url"}`. ANSI-коды в ошибках yt-dlp стрипаются → `400` с понятным сообщением. Невалидный/недоступный URL → `400`.

```bash
curl "http://127.0.0.1:8000/api/yt-dlp/info?url=https://www.youtube.com/watch?v=dQw4w9WgXcQ"
# → {"title": "Rick Astley - Never Gonna Give You Up", "duration": 213, ...}
```

`POST /api/yt-dlp` — body: `{"url": "...", "language": "ru", "provider": "faster-whisper", "model": "small"}` (поля `language`/`provider`/`model` опциональны). SSE-стрим:

| Event | `type` | `payload` |
|---|---|---|
| `info` | `"info"` | `{title, duration, thumbnail, uploader, webpage_url}` |
| `downloading` | `"progress"` | `{phase: "downloading", percent, filename, ...}` |
| `transcribing` | `"progress"` | `{phase: "transcribing", percent, segment: {start, end, text}}` |
| `done` | `"done"` | `{text, segments, info, file}` |
| `error` | `"error"` | `{detail}` |

Скачивается лучшее доступное аудио (m4a/webm/best) → конвертируется в WAV через `FFmpegExtractAudio` (lossless) → обрабатывается как обычный файл. Скачанный WAV остаётся в `data/transcripts/_yt-dlp/<title>.wav` (опционально можно чистить).

### Системный звук / loopback (v1.5.7)

`GET /api/system-audio/devices` — `{"available": true, "devices": [{"id": 0, "name": "Headphones (loopback)"}, ...]}`. Если soundcard не установлен или нет loopback-устройств → `{"available": false, "reason": "..."}` (HTTP `200`, не ошибка).

`POST /api/system-audio/start` — body: `{"device_id": 0}`. Запускает `SystemAudioRecorder` в фоновом `threading.Thread` (16kHz mono, 100ms чанки). Ответ: `{"started": true, "device": "Headphones", "elapsed_sec": 0.1}`. Если уже идёт запись → `409 Conflict`. `400` если device_id невалидный или не loopback.

`POST /api/system-audio/stop` — body: `{"save_to": "transcripts" | "voice-memos"}` (опционально, default `"transcripts"`). Останавливает запись (max 15с wait), сохраняет WAV во временный файл, транскрибирует активным провайдером, результат пишется в `data/<save_to>/`. SSE-стрим с теми же событиями что и `/transcribe` (`progress` → `done`). В UI: `save_to: voice-memos` помещает в голосовые заметки.

Single-instance lock в `server.py` — параллельная запись невозможна. `400` если запись не была запущена.

### Self-update (v1.5.8)

`GET /api/updates/state` — возвращает:

```json
{
  "current_version": "9397dc5",
  "latest_version": "f123456",
  "available": true,
  "should_notify": true,
  "dismissed_version": null,
  "last_check": "2026-08-20T10:30:00Z",
  "last_apply_at": null,
  "last_apply_result": null,
  "last_apply_version": null,
  "check_error": null,
  "auto_update_enabled": false
}
```

`should_notify` = `available AND dismissed_version != latest` (computed; UI использует это для показа баннера).

`POST /api/updates/check-now` — `git fetch origin main` + `git rev-list --count HEAD..origin/main` → обновляет state. Ответ: `{"ok": true, "available": true, "current": "...", "latest": "..."}` или `{"ok": true, "available": false, "message": "Up to date"}`.

`POST /api/updates/dismiss` — помечает текущую `latest_version` как dismissed (юзер нажал «Позже»). Баннер не показывается до новой версии. Ответ: `{"ok": true, "dismissed_version": "f123456"}`.

`POST /api/updates/apply` — `git pull --ff-only` + `pip install --upgrade -r requirements.txt`. Single-instance lock (2с timeout). Ответ:

```json
{
  "ok": true,
  "old_version": "9397dc5",
  "new_version": "f123456",
  "restart": false,
  "restart_in_sec": null
}
```

Если `auto_update_app=true` (через `data/config.json` или POST `/api/config {"auto_update_app": true}`) → `restart: true, restart_in_sec: 2` и через 2 секунды сервер делает `os.execv(PROJECT_ROOT / "server.py")`. UI ловит это polling'ом `/health`.

При ошибке: `{"ok": false, "result": "git_failed" | "pip_failed" | "exception", "log": [...]}`.

`GET /api/updates` (legacy) — `tools/update.check_all_updates()`: проверка приложения + моделей. `?stream=1` → SSE. Оставлен для обратной совместимости; новый код должен использовать `/api/updates/state` + `/api/updates/{check-now,dismiss,apply}`.

### Провайдеры, модели, установка

`POST /api/provider/install` — тело `{"provider": "whisper-cpp"}`; ответ `{"ok": true, "log": [...]}` (последние ~50 строк вывода pip).

`POST /api/provider/load` — тело `{"provider", "model", "device"}` (пустые поля берутся из конфига); ответ `{"ok": true, "loaded": {...}}`. Модель должна быть скачана.

`GET /api/model/check?provider=faster-whisper&model=small` — `{"provider", "model", "source", "has_update", "local_exists", "local_sha", "remote_sha", "last_modified", ...}`.

`POST /api/updates/app` (legacy) — `{"app_pull": {...}, "deps_upgrade": {...}, "log": [...], "providers_after": [...]}`. DEPRECATED, используйте `/api/updates/apply`.

### Экспорт субтитров (v1.5.6)

`GET /api/transcripts/{name}/export?format=srt|vtt|json|txt` — конвертация сохранённых сегментов в стандартные форматы. Имя берётся из ответа `/transcribe` (поле `file`), URL-кодируется через `urllib.parse.quote`.

| format | media_type | Описание |
|---|---|---|
| `srt` | `application/x-subrip; charset=utf-8` | SubRip, `HH:MM:SS,mmm` (запятая). |
| `vtt` | `text/vtt; charset=utf-8` | WebVTT, `HH:MM:SS.mmm` (точка), с `WEBVTT` заголовком. |
| `json` | `application/json; charset=utf-8` | `{"version": 1, "language", "provider", "model", "duration", "segments": [{start, end, text}, ...]}`. |
| `txt` | `text/plain; charset=utf-8` | Plain text из `.txt` (без `#` header). |

Ответ — `Response(content, media_type=..., headers={"Content-Disposition": "attachment; filename=<stem>.<ext>"})` — скачивание через `-OJ` или аналог. Невалидный `format` → `400`.

Если `*.segments.json` sidecar отсутствует (старая расшифровка) — генерируется «плоский» SRT/VTT (один сегмент, длительность ~15 символов/сек как грубая оценка).

### SSE-эндпоинты

Общий формат события (каждое — строка `data: <json>\n\n`):

```json
{ "type": "progress|done|error", "percent": 0-100, "payload": { ... } }
```

- `POST /transcribe` — события: `progress` (сегмент: `{start, end, text}`), финальное `done` с `payload: {text, segments, info, file}`; при ошибке — `error`.
- `POST /api/model/download` — `progress` (`payload` — статус скачивания), `done` с путём к модели, `error`.
- `GET /api/updates?stream=1` — `progress` на каждую проверенную модель (`payload: {phase, label, percent, done, total, provider, model}`), затем `done` с полным отчётом `{app, models}`.
- `POST /api/yt-dlp` — `info` → `progress` (downloading/transcribing) → `done`/`error`.
- `POST /api/system-audio/stop` — `info` → `progress` (сегменты) → `done`/`error`.

### POST /transcribe (multipart/form-data)

| Поле | Обязательное | Описание |
|---|---|---|
| `file` | да | Аудиофайл (`mp3`, `wav`, `m4a`, `ogg`, `flac`, `webm`, ...) |
| `language` | нет | `ru` (по умолчанию) \| `en` \| `auto` \| ... — поддерживаются языки провайдера |
| `provider` | нет | Переопределение провайдера (по умолчанию — из конфига) |
| `model` | нет | Переопределение модели |
| `device` | нет | `cpu` \| `cuda` |

Пример:

```bash
curl -N -F "file=@speech.mp3" -F "language=ru" http://127.0.0.1:8000/transcribe
```

Пример потока:

```
data: {"type":"progress","percent":12,"payload":{"start":0,"end":3.2,"text":"Добрый день"}}

data: {"type":"done","percent":100,"payload":{"text":"Добрый день...","segments":[{"start":0,"end":3.2,"text":"Добрый день"}],"info":{"language":"ru","language_probability":0.98,"duration":42.5},"file":"2026-08-19_speech.mp3.txt"}}
```

После успешной транскрибации расшифровка сохраняется в `data/transcripts/` (см. [CONFIGURATION.md](CONFIGURATION.md), ключ `cleanup_after_days`) + sidecar `<stem>.segments.json`. Финальный `done` event содержит `file` — имя для последующего `/api/transcripts/{name}/export`.

## Коды ошибок

| Код | Когда | Формат ответа |
|---|---|---|
| `400` | Невалидное тело (`{"days": "abc"}`, отсутствует `provider`/`model`); невалидный URL для yt-dlp; неподдерживаемый формат экспорта | `{"detail": "..."}` |
| `404` | Неизвестный провайдер (в `detail` — список доступных); модель не скачана; файл не найден | `{"detail": "..."}` |
| `409` | Параллельный `/api/system-audio/start` пока уже идёт запись | `{"detail": "..."}` |
| `412` | Провайдер не установлен / не готов (нет CUDA у Parakeet и т.п.) | `{"detail": "..."}` |
| `502` | Все провайдеры перевода недоступны | `{"detail": "...", "providers_tried": [...]}` |
| `503` | Сервер ещё стартует (модель ещё не инициализирована) | `{"detail": "..."}` |

## Rate limiting

Ограничения частоты запросов не настроены. Транскрибация и скачивание моделей — тяжёлые операции; в памяти одновременно держится одна модель, параллельные запросы транскрибации сериализуются на этапе загрузки модели (но не на этапе самой транскрибации). Single-instance lock для system audio и self-update.
