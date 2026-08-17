<!-- generated-by: gsd-doc-writer -->
# Конфигурация Autrau

Autrau настраивается двумя способами: **файл конфигурации** (`data/config.json`, основной — его меняет UI) и **переменные окружения** (сервер и вспомогательные скрипты).

## Переменные окружения

| Переменная | Обязательная | По умолчанию | Описание | Читает код |
|---|---|---|---|---|
| `AUTRAU_HOST` | нет | `127.0.0.1` | Адрес прослушивания сервера | `server.py:51` |
| `AUTRAU_PORT` | нет | `8000` | Порт сервера | `server.py:52` |
| `MAX_UPLOAD_MB` | нет | `500` | Максимальный размер загрузки, МБ | `server.py:53` *(объявлена, но не применяется в текущей версии)* |
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
  "cleanup_after_days": 0
}
```

| Ключ | Тип | По умолчанию | Описание |
|---|---|---|---|
| `provider` | string | `faster-whisper` | Активный провайдер: `faster-whisper` \| `whisper-cpp` \| `parakeet` |
| `model` | string | `small` | Модель внутри провайдера (зависит от провайдера) |
| `device` | string | `cpu` | Устройство: `cpu` \| `cuda` |
| `language` | string | `ru` | Язык распознавания по умолчанию (`auto` = автоопределение) |
| `beam_size` | int | `5` | Beam size (faster-whisper) |
| `compute_type` | string | `auto` | Тип вычислений: `auto` \| `int8` \| `float16` \| `float32` |
| `check_updates_on_start` | bool | `true` | Проверять обновления при старте сервера |
| `auto_update_app` | bool | `false` | Автоматически обновлять приложение при старте *(зарезервировано)* |
| `cleanup_after_days` | int | `0` | Авто-очистка расшифровок: `0` = не удалять; `N>0` = удалять расшифровки старше N дней |

`cleanup_after_days` применяется фоновым циклом (каждые 6 часов) и при ручном `POST /api/cleanup`.

## Обязательные настройки

Обязательных настроек нет: при отсутствии файла или нечитаемом JSON сервер запускается со встроенными значениями по умолчанию (в лог пишется предупреждение). Файл пересоздаётся при первом запуске.

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
