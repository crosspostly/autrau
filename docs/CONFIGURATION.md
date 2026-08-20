<!-- generated-by: gsd-doc-writer -->
# Конфигурация Autrau

Autrau настраивается двумя способами: **файл конфигурации** (`data/config.json`, основной — его меняет UI) и **переменные окружения** (сервер и вспомогательные скрипты).

## Переменные окружения

| Переменная | Обязательная | По умолчанию | Описание | Читает код |
|---|---|---|---|---|
| `AUTRAU_HOST` | нет | `127.0.0.1` | Адрес прослушивания сервера | `server.py:51` |
| `AUTRAU_PORT` | нет | `8000` | Порт сервера | `server.py:52` |
| `MAX_UPLOAD_MB` | нет | `500` | Максимальный размер загрузки, МБ; файлы больше лимита отклоняются с `413` и понятным сообщением | `server.py:61` |
| `AUTRAU_CONFIG` | нет | `data/config.json` | Путь к файлу конфигурации | `tools/config.py:40` |
| `HF_HOME` | нет | `~/.cache/huggingface` | Каталог кэша моделей Hugging Face (faster-whisper и parakeet) | `providers/faster_whisper.py:223`, `providers/parakeet.py:117` |
| `AUTRAU_SKIP_UPDATE_CHECK` | нет | `0` | Пропустить проверку обновлений при старте | `start.bat` (batch-скрипт) |
| `AUTRAU_PROVIDER`, `AUTRAU_MODEL`, `AUTRAU_DEVICE` | нет | — | **Зарезервированы.** Перечислены в `.env.example`, но текущим кодом **не читаются** — провайдер/модель/устройство берутся из `data/config.json` | — |

Обратите внимание: `.env`-файл сам по себе кодом не загружается (python-dotenv не используется). Переменные действуют, только если установлены в окружении процесса (системные переменные, PowerShell `$env:`, `setx`) или заданы в `start.bat` (`AUTRAU_PORT`/`AUTRAU_HOST` устанавливаются там перед запуском).

## Файл конфигурации

Основной источник настроек — `data/config.json` (создаётся автоматически при первом запуске, gitignored). Путь можно переопределить через `AUTRAU_CONFIG`.

```json
{
  "provider": "faster-whisper",
  "model": "small",
  "device": "cpu",
  "language": "ru",
  "beam_size": 5,
  "compute_type": "auto",
  "check_updates_on_start": true,
  "auto_update_app": false,
  "cleanup_after_days": 0,
  "hotkey": "Ctrl+Shift+R",
  "voice_memo_dir": "data/voice-memos/",
  "voice_memo_cleanup_after_days": 7,
  "translate_to_en": false,
  "translation_provider": "argos",
  "translation_fallback": "libretranslate",
  "libretranslate_url": "",
  "libretranslate_key": "",
  "minimax_key": "",
  "telegram_bot_token": "",
  "telegram_allowed_chat_ids": [],
  "telegram_api_url": ""
}
```

| Ключ | Тип | По умолчанию | Описание |
|---|---|---|---|
| `provider` | string | `faster-whisper` | Активный провайдер: `faster-whisper` \| `whisper-cpp` \| `parakeet` \| `parakeet-onnx` |
| `model` | string | `small` | Модель внутри провайдера (зависит от провайдера) |
| `device` | string | `cpu` | Устройство: `cpu` \| `cuda` |
| `language` | string | `ru` | Язык распознавания по умолчанию (`auto` = автоопределение) |
| `beam_size` | int | `5` | Beam size (faster-whisper) |
| `compute_type` | string | `auto` | Тип вычислений: `auto` \| `int8` \| `float16` \| `float32` |
| `check_updates_on_start` | bool | `true` | Проверять обновления при старте сервера |
| `auto_update_app` | bool | `false` | **v1.5.8.** Автоматически применять обновления: `git pull --ff-only` + `pip install -U` + restart через `os.execv`. По умолчанию OFF (opt-in) — пользователь видит баннер в UI и жмёт «Обновить» вручную. |
| `update_check_interval_hours` | int | `6` | **v1.5.8.** Как часто background scheduler проверяет обновления (минимум 1, максимум 168 = 1 неделя). |
| `cleanup_after_days` | int | `0` | Авто-очистка расшифровок из `data/transcripts/`: `0` = не удалять; `N>0` = удалять старше N дней |
| `hotkey` | string | `Ctrl+Shift+R` | **v1.5.** Сочетание клавиш для записи голосовой заметки. Настраивается в UI. Работает только когда вкладка в фокусе. Формат: `Ctrl+Shift+R` (модификаторы + клавиша через `+`). |
| `voice_memo_dir` | string | `data/voice-memos/` | **v1.5.** Папка для голосовых заметок. Создаётся автоматически. |
| `voice_memo_cleanup_after_days` | int | `7` | **v1.5.** Авто-очистка голосовых заметок: `0` = не удалять; `N>0` = удалять старше N дней. Отдельный лимит от `cleanup_after_days`. |
| `translate_to_en` | bool | `false` | **v1.5.** Если `true` — после каждой расшифровки создаётся `<имя>.en.txt` (если язык оригинала не английский). В UI — галочка в шестерёнке → «3.5 🌐 Перевод на английский». |
| `translation_provider` | string | `argos` | **v1.5.** Провайдер перевода: `argos` (локально, ~336 МБ en↔ru, **работает из коробки** после `📥 Установить Argos` в UI) \| `libretranslate` (⚠️ публичные инстансы мертвы, только self-hosted) \| `minimax` (платный API, ключ в `~/.minimax/auth.json`) |
| `translation_fallback` | string | `libretranslate` | **v1.5.** Fallback провайдер если primary не сработал. Пустая строка = без fallback. |
| `libretranslate_url` | string | `""` | **v1.5.** URL LibreTranslate. Пусто = `https://libretranslate.com/` (⚠️ мёртв в 2025). |
| `libretranslate_key` | string | `""` | **v1.5.** API-ключ LibreTranslate (если self-hosted требует). |
| `minimax_key` | string | `""` | **v1.5.** API-ключ MiniMax. Пусто = авто-поиск в `~/.minimax/auth.json`. |
| `telegram_bot_token` | string | `""` | **v1.7.** Токен Telegram-бота от [@BotFather](https://t.me/BotFather). Пусто = `start_telegram_bot.bat` откажется стартовать с подсказкой. Можно переопределить через env `TELEGRAM_BOT_TOKEN`. |
| `telegram_allowed_chat_ids` | list\|string | `[]` | **v1.7.** Whitelist chat_id пользователей. `[]` = бот блокирует всех; `[123, 456]` = только эти; строка `"any"` = пропускать всех (⚠️ только для dev); строка `"123,456"` = парсится как CSV. |
| `telegram_api_url` | string | `""` | **v1.7.** URL autrau API для бота. Пусто = `http://127.0.0.1:8000`. Можно переопределить через env `TELEGRAM_API_URL`. |

`cleanup_after_days` применяется фоновым циклом (каждые 6 часов) и при ручном `POST /api/cleanup`.

## Обязательные настройки

Обязательных настроек нет: при отсутствии файла или нечитаемом JSON сервер запускается со встроенными значениями по умолчанию (в лог пишется предупреждение). Файл пересоздаётся при первом запуске.

## Дополнительные зависимости (опциональные)

Конфиг не управляет установкой доп. пакетов — их надо ставить вручную в venv сервера:

| Пакет | Нужен для | Как установить |
|-------|-----------|----------------|
| `ffmpeg` | Извлечение звука из видео (mp4/mkv/mov) | `winget install Gyan.FFmpeg` (Windows) / `apt install ffmpeg` (Linux) / `brew install ffmpeg` (macOS) |
| `argostranslate` + `langdetect` | Локальный перевод ru→en (Argos Translate) | `pip install argostranslate langdetect` (или кнопка «📥 Установить Argos» в UI) |
| `yt-dlp` | URL → транскрипция (YouTube/Vimeo/etc) | `pip install yt-dlp` (только в venv сервера) |
| `soundcard` | Захват системного звука (Windows WASAPI) | `pip install soundcard` (нужен CFFI; на Windows обычно работает из коробки) |
| `pywhispercpp` | Whisper.cpp провайдер (опционально) | `pip install pywhispercpp` |
| `nemo_toolkit[asr]` | Parakeet v3 через NVIDIA NeMo (опционально, ~2-3 ГБ) | `pip install nemo_toolkit[asr]` |

Эти пакеты перечислены в `requirements.txt` только базовые (`yt-dlp>=2024.0.0` уже добавлен в v1.5.7, `soundcard` — ставится вручную).

## Приоритет значений

1. **Аргументы запроса** (`POST /transcribe`: `provider`, `model`, `device`, `language`) — переопределяют всё для одного запроса.
2. **Env-переменные сервера** (`AUTRAU_HOST`, `AUTRAU_PORT`) — только хост/порт.
3. **`data/config.json`** — провайдер, модель, устройство, язык и остальные настройки UI.
4. **Встроенные дефолты** (`DEFAULTS` в `tools/config.py:19`).

## Переопределение для разных окружений

Отдельных файлов `.env.development`/`.env.production` нет. Если нужно несколько «профилей» конфигурации (например, для теста), укажите другой файл:

```powershell
$env:AUTRAU_CONFIG = "data\config-test.json"
python server.py
```

Для смены порта/хоста без правки файлов:

```powershell
$env:AUTRAU_PORT = "8001"
$env:AUTRAU_HOST = "0.0.0.0"
python server.py
```

> ⚠️ Прослушивание на `0.0.0.0` открывает сервер в локальной сети. По умолчанию Autrau слушает только `127.0.0.1`; API не требует аутентификации — не выставляйте его в интернет как есть.
