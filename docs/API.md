<!-- generated-by: gsd-doc-writer -->
# HTTP API Autrau

Базовый URL: `http://127.0.0.1:8000` (по умолчанию; настраивается через `AUTRAU_HOST`/`AUTRAU_PORT`).

## Аутентификация

Аутентификации нет. Приложение рассчитано на локальный запуск и по умолчанию слушает только `127.0.0.1`. CORS открыт (`allow_origins=["*"]`) — не выставляйте сервер в интернет без защиты.

## Обзор эндпоинтов

| Метод | Путь | Описание |
|---|---|---|
| `GET` | `/` | Web UI (HTML) |
| `GET` | `/docs` | Swagger UI (auto-generated OpenAPI) |
| `GET` | `/openapi.json` | OpenAPI schema (JSON) |
| `GET` | `/health` | Статус сервера, версия, загруженная модель |
| `GET` | `/api/providers` | Провайдеры, их модели, статус установки, активный выбор |
| `GET` | `/api/config` | Текущая конфигурация (JSON) |
| `POST` | `/api/config` | Обновить ключи конфигурации |
| `POST` | `/api/cleanup` | Удалить расшифровки старше N дней |
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
| `POST` | `/api/translate` | Перевести текст (body: `{text, target?, provider?, fallback?}`) |
| `GET` | `/api/translate/providers` | Какие провайдеры перевода доступны прямо сейчас |
| `POST` | `/api/translate/install-argos` | Установить `argostranslate`+`langdetect`+обе модели en_ru/ru_en в фоне |
| `GET` | `/api/updates` | Проверка обновлений (JSON; `?stream=1` — SSE-прогресс) |
| `POST` | `/api/updates/app` | Self-update: `git pull --ff-only` + `pip install --upgrade -r requirements.txt` (DEPRECATED → use `/api/updates/apply`) |
| `GET` | `/api/updates/state` | Persistent state: `current/latest/available/should_notify/auto_update_enabled` (v1.5.8) |
| `POST` | `/api/updates/check-now` | Force check: обновляет state без auto-apply (v1.5.8) |
| `POST` | `/api/updates/dismiss` | Dismiss banner для текущей `latest_version` (v1.5.8) |
| `POST` | `/api/updates/apply` | Apply update: git pull + pip upgrade. Если `auto_update_app=true` → restart через `os.execv` (v1.5.8) |
| `POST` | `/api/model/download` | Скачать модель (SSE-прогресс) |
| `GET` | `/api/model/check` | Проверить обновление одной модели |
| `POST` | `/api/provider/load` | Загрузить провайдера+модель в память |
| `POST` | `/api/provider/install` | Установить провайдера через pip |
| `POST` | `/transcribe` | Транскрибация аудио (SSE-поток) |

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

`POST /api/provider/install` — тело `{"provider": "whisper-cpp"}`; ответ `{"ok": true, "log": [...]}` (последние ~50 строк вывода pip).

`POST /api/provider/load` — тело `{"provider", "model", "device"}` (пустые поля берутся из конфига); ответ `{"ok": true, "loaded": {...}}`. Модель должна быть скачана.

`GET /api/model/check?provider=faster-whisper&model=small` — `{"provider", "model", "source", "has_update", "local_exists", "local_sha", "remote_sha", "last_modified", ...}`.

`POST /api/updates/app` — `{"app_pull": {...}, "deps_upgrade": {...}, "log": [...], "providers_after": [...]}`.

### SSE-эндпоинты

Общий формат события (каждое — строка `data: <json>\n\n`):

```json
{ "type": "progress|done|error", "percent": 0-100, "payload": { ... } }
```

- `POST /transcribe` — события: `progress` (сегмент: `{start, end, text}`), финальное `done` с `payload: {text, segments, info}`; при ошибке — `error`.
- `POST /api/model/download` — `progress` (`payload` — статус скачивания), `done` с путём к модели, `error`.
- `GET /api/updates?stream=1` — `progress` на каждую проверенную модель (`payload: {phase, label, percent, done, total, provider, model}`), затем `done` с полным отчётом `{app, models}`.

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

data: {"type":"done","percent":100,"payload":{"text":"Добрый день...","segments":[{"start":0,"end":3.2,"text":"Добрый день"}],"info":{"language":"ru","language_probability":0.98,"duration":42.5}}}
```

После успешной транскрибации расшифровка сохраняется в `data/transcripts/` (см. [CONFIGURATION.md](CONFIGURATION.md), ключ `cleanup_after_days`).

## Коды ошибок

| Код | Когда | Формат ответа |
|---|---|---|
| `400` | Невалидное тело (`{"days": "abc"}`, отсутствует `provider`/`model`) | `{"detail": "..."}` |
| `404` | Неизвестный провайдер (в `detail` — список доступных); модель не скачана | `{"detail": "..."}` |
| `412` | Провайдер не установлен / не готов (нет CUDA у Parakeet и т.п.) | `{"detail": "..."}` |
| `503` | Сервер ещё стартует (модель ещё не инициализирована) | `{"detail": "..."}` |

## Rate limiting

Ограничения частоты запросов не настроены. Транскрибация и скачивание моделей — тяжёлые операции; в памяти одновременно держится одна модель, параллельные запросы транскрибации сериализуются на этапе загрузки модели (но не на этапе самой транскрибации).
