<!-- generated-by: gsd-doc-writer -->
# 🎙️ Autrau

**Локальный мульти-провайдерный транскрибатор аудио. Без облака, без загрузки записей на чужие серверы.**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![CI](https://img.shields.io/github/actions/workflow/status/crosspostly/autrau/ci.yml?label=CI)](.github/workflows/ci.yml)

Переводит речь из аудио- и видеофайлов (`mp3`, `wav`, `m4a`, `ogg`, `flac`, `webm`, `mp4`, `mkv`, `mov`) в текст локально — у видео звук извлекается автоматически (нужен ffmpeg). Два бэкенда на выбор (ещё два доступны для продвинутых пользователей — см. таблицу):

| Провайдер | В UI | Что внутри | Моделей | RAM | GPU | Особенности |
|---|---|---|---|---|---|---|
| **Whisper.cpp** | ✅ | pywhispercpp (C++ биндинги) | 2 (tiny, large-v3) | 1 ГБ | нет | Без PyTorch, очень лёгкий |
| **Parakeet v3 (ONNX/DirectML)** | ✅ | onnx-asr + DirectML | 1 (parakeet-tdt-0.6b-v3) | 1.5 ГБ | любой GPU/CPU | SOTA 2025–2026, 25 языков, без CUDA |
| **Faster-Whisper** | ❌ (скрыт) | CTranslate2 | 15 | 2 ГБ | NVIDIA | CPU и GPU, многоязычный |
| **Parakeet TDT v3** | ❌ (скрыт) | NVIDIA NeMo | 2 | 4 ГБ | **NVIDIA** | Тот же SOTA с CUDA |

**Почему Faster-Whisper и Parakeet-NeMo скрыты из UI:** оба требуют NVIDIA GPU для ускорения. На AMD/Intel-аппаратуре они работают только на CPU и не дают преимущества. Если у вас NVIDIA — переключитесь в config.json вручную (`provider: "faster-whisper"`).

Модели скачиваются напрямую с официальных реестров Hugging Face:
`ggerganov/whisper.cpp` (ggml-`*.bin`), `istupakov/parakeet-tdt-0.6b-v3-onnx` (int8, ~640 МБ).

---

## ✨ Возможности

- 🎙️ **Голосовые заметки** — нажмите `Ctrl+Shift+R` (настраивается) и говорите: запись → авто-транскрипция → сохраняется в `data/voice-memos/` (отдельный раздел «Голосовые заметки» с собственной политикой авто-очистки, 7 дней по умолчанию)
- 🌐 **Автоперевод на английский** (opt-in, по умолчанию **выключен**) — после каждой расшифровки автоматически создаётся `<имя>.en.txt` и badge 🇬🇧 EN рядом с файлом. **Три провайдера:** **Argos Translate** (локально, ~336 МБ en↔ru, **работает из коробки** после `📥 Установить Argos` в UI), **LibreTranslate** (⚠️ публичные инстансы мертвы в 2025 — только self-hosted), **MiniMax** (платный API, ключ в `~/.minimax/auth.json`). Настраивается в шестерёнке → «3.5 🌐 Перевод на английский».
- 🧠 **2 движка, 3 модели** — Whisper.cpp (tiny 75 МБ, large-v3 2.9 ГБ) или Parakeet v3 ONNX (640 МБ). После транскрипции — автоперевод на английский через локальный Argos Translate (~336 МБ en↔ru, без облака)
- 📁 **Очередь файлов** — выберите несколько, жмите «Транскрибировать», они обработаются по очереди
- ⭐ **Избранное** — помеченные расшифровки никогда не удаляются авто-очисткой
- 🗑 **Bulk-удаление** — чекбокс «Выбрать все» в обеих секциях (файлы + голосовые заметки)
- 🎬 **Видео тоже работает** — mp4/mkv/mov/avi/webm: звук извлекается автоматически через ffmpeg
- 🔄 **Авто-обновления** (v1.5.8) — проверка новых коммитов + авто-apply через `git pull --ff-only` + `pip install -U`. По умолчанию **выключено** (opt-in в шестерёнке → «Автоматически обновлять приложение»). При включении — сервер сам обновляется и перезапускается через `os.execv`. Баннер «🎉 Доступно обновление» в UI для ручного apply.
- 🧹 **Авто-очистка расшифровок** — старые расшифровки удаляются автоматически по возрасту (или вручную)
- 🗂 **Архив расшифровок** — каждая расшифровка сохраняется в `data/transcripts/`; голосовые заметки — в `data/voice-memos/` (отдельный таб в UI); в обоих разделах — чекбоксы, bulk-удаление, кнопка «Открыть папку». Избранные (★) никогда не удаляются авто-очисткой.
- 🖥 **Web UI** — без сборщиков, один `index.html`; drag-and-drop, тёмная тема
- 💻 **CLI** (v1.5.7) — `python -m autrau.cli transcribe|batch|providers|models|status|health` — используй autrau из терминала, в скриптах, или через `python -m autrau.cli batch ./audio/`
- 🔗 **URL → транскрипция** (v1.5.7) — вставь YouTube / Vimeo / Twitter / 1500+ других URL → yt-dlp скачает аудио → autrau расшифрует. UI: collapsible «🔗 Или вставьте URL» в секции загрузки
- 🔊 **Системный звук** (v1.5.7) — захват того что играет в колонках (Windows WASAPI loopback): YouTube, Zoom, любой аудио в системе → расшифровка. UI: «🔊 Или захватить системный звук»
- 📤 **Экспорт субтитров** (v1.5.6) — SRT / VTT / JSON / TXT из каждой расшифровки. Использует sidecar `<name>.segments.json` с таймкодами от ASR. Кнопка «📤 Экспорт ▾» в карточке результата.
- 📱 **Telegram agent bot** (v1.7) — отдельный процесс, голосовые/аудио из чата → авто-расшифровка + EN-перевод. Команды `/status`, `/providers`, `/check`, `/update`, `/ask <вопрос>` (агент-режим для usability/QA). Whitelist chat_id по умолчанию. Запуск: `start_telegram_bot.bat` после `pip install 'python-telegram-bot>=20.0,<22.0'`.
- 🖥 **Electron desktop** (v1.6) — отдельный репо [`crosspostly/autrau-desktop`](https://github.com/crosspostly/autrau-desktop). Нативное окно с always-on-top, system tray, **глобальный хоткей Alt+R** (работает вне браузера), single instance lock, sidecar к autrau-server. Dev-режим: `npm start`. Portable .exe → v1.6.2.

---

## ⚡ Запуск в 1 клик (Windows)

1. Установите [Python 3.10+](https://www.python.org/downloads/) (при установке — галка **Add Python to PATH**)
2. Двойной клик по **`start.bat`**

Скрипт сам создаст venv, поставит зависимости, проверит Python/ffmpeg/git, покажет состояние провайдеров и запустит сервер: **http://127.0.0.1:8000/**.

### Что ставится автоматически (первый запуск)

| Компонент | Откуда | Ставится сам? |
|---|---|---|
| Python 3.10+ | [python.org](https://www.python.org/downloads/) | ❌ вручную, нужен до запуска |
| ffmpeg (обязателен для видео) | `winget install Gyan.FFmpeg` | ❌ вручную; при старте только проверяется |
| git (для self-update) | [git-scm.com](https://git-scm.com) | ❌ вручную; при старте только проверяется |
| venv + база (fastapi, uvicorn, python-multipart, huggingface-hub) | `requirements.txt` | ✅ автоматически при первом запуске |
| **Faster-Whisper** (провайдер по умолчанию) | `requirements.txt` | ✅ автоматически |
| Whisper.cpp / Parakeet (NeMo) / Parakeet v3 (ONNX) | — | ✅ одной кнопкой «⬇ Установить провайдер» в UI |
| **Telegram agent bot** (v1.7) | `pip install 'python-telegram-bot>=20.0,<22.0'` | ❌ вручную (opt-in, нужен токен) |

Каждый запуск заново проверяет Python, ffmpeg, git, наличие зависимостей и статус всех провайдеров — если чего-то не хватает, показывает предупреждение до старта сервера.

## 📦 Установка вручную

```powershell
git clone https://github.com/crosspostly/autrau.git
cd autrau
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python server.py
```

Опциональные провайдеры:

```powershell
# whisper.cpp — без PyTorch, лёгкий
pip install pywhispercpp

# Parakeet v3 — нужен NVIDIA GPU + CUDA
pip install -r requirements-parakeet.txt

# Parakeet v3 (ONNX/DirectML) — без NVIDIA: любой GPU через DirectX или CPU
pip install onnx-asr[hub] onnxruntime-directml

# Translation: Argos Translate (локально, en↔ru, ~336 МБ)
pip install argostranslate langdetect
py -3.13 -c "from argostranslate import package; package.update_package_index(); [package.get_available_packages() | None for _ in [None]]"  # опционально — UI установит сам
# Или в UI: шестерёнка → «3.5 🌐 Перевод» → «📥 Установить Argos»
```

## 🎧 Использование

1. Откройте **http://127.0.0.1:8000/** — закиньте аудио- или видеофайл (mp4/mkv/mov…) в окно
2. Выберите провайдера/модель (или оставьте дефолт: `faster-whisper / small`)
3. Нажмите «Транскрибировать» — прогресс идёт по сегментам, в конце текст можно скопировать

У видео звук извлекается автоматически (ffmpeg → 16 кГц моно wav); в статусе появится «🎬 извлекаю звук из видео …».

**Через CLI** (v1.5.7+, тот же сервер):

```powershell
# Один файл
.\.venv\Scripts\python.exe -m autrau.cli transcribe data\test_ru.mp3 --output out.txt

# Пакетная обработка директории
.\.venv\Scripts\python.exe -m autrau.cli batch data\ --pattern "*.{mp3,wav}" --output .\out\

# Список провайдеров / моделей
.\.venv\Scripts\python.exe -m autrau.cli providers
.\.venv\Scripts\python.exe -m autrau.cli models --provider parakeet-onnx

# Статус / проверка
.\.venv\Scripts\python.exe -m autrau.cli status
.\.venv\Scripts\python.exe -m autrau.cli health
```

Или через API:

```powershell
# Транскрибация (SSE-поток)
curl -N -F "file=@speech.mp3" -F "language=ru" http://127.0.0.1:8000/transcribe

# Из URL (YouTube/Vimeo/Twitter через yt-dlp)
curl -N -X POST -H "Content-Type: application/json" `
  -d '{"url": "https://www.youtube.com/watch?v=..."}' `
  http://127.0.0.1:8000/api/yt-dlp

# Системный звук (loopback)
curl -X POST -H "Content-Type: application/json" -d '{"device_id": 0}' http://127.0.0.1:8000/api/system-audio/start
# ... подождать 10 сек ...
curl -X POST -H "Content-Type: application/json" -d '{"save_to": "voice-memos"}' http://127.0.0.1:8000/api/system-audio/stop

# Экспорт SRT/VTT/JSON
curl "http://127.0.0.1:8000/api/transcripts/2026-08-19_voice.mp3.txt/export?format=srt" -o subtitles.srt

# Список провайдеров и моделей
curl http://127.0.0.1:8000/api/providers

# Состояние обновлений
curl http://127.0.0.1:8000/api/updates/state

# Применить обновление
curl -X POST http://127.0.0.1:8000/api/updates/apply

# Swagger UI (auto-generated docs)
# Откройте http://127.0.0.1:8000/docs
```

После транскрибации расшифровка автоматически сохраняется в `data/transcripts/` — файл `<дата>_<время>_<имя>.txt` с шапкой (файл, дата, модель, язык).

## 🔄 Обновления

```powershell
update.bat
```

- `git pull --ff-only` + `pip install --upgrade -r requirements.txt`
- Проверка новых версий моделей на Hugging Face

В UI вкладка **🔄 Обновления** показывает новые коммиты и новые версии моделей; `/api/updates?stream=1` стримит прогресс. Проверяются **только скачанные на диск модели** (нескачанные ни на что не влияют, и не тратится время на десятки запросов к Hugging Face). Кнопка «⬇ Обновить приложение» делает то же, что `update.bat`.

## 📱 Telegram agent bot (v1.7)

```powershell
pip install "python-telegram-bot>=20.0,<22.0"
# 1. Создайте бота через @BotFather, получите токен
# 2. В data/config.json:
#    "telegram_bot_token": "123456:ABC...",
#    "telegram_allowed_chat_ids": [ваш chat_id],  # узнать: /start → бот пришлёт chat_id
# 3. Двойной клик по start_telegram_bot.bat
```

Бот как «агент для usability»:

- 🎙 **Голосовое / аудио из чата** → скачивание → ffmpeg (ogg→wav) → `/transcribe` → ответ + EN-перевод
- 📋 **Команды:** `/start`, `/help`, `/status`, `/providers`, `/config`, `/lang ru|en|auto`, `/favorites`, `/export srt|vtt|json|txt`, `/check` (диагностика), `/diag <comp>` (granular: python/ffmpeg/git/deps/providers/updates), `/logs [N] [err]` (хвост лога сервера), `/test [provider] [lang]` (реальная транскрипция test_ru.mp3), `/update` (проверка), `/update apply` (применить)
- 🤖 **Агент-режим:** `/ask <вопрос>` или просто вопросительное сообщение (например «как установить argos?», «медленно работает», «не работает перевод», «где логи?», «как сделать тест?») — бот матчит по 13 FAQ-паттернам и отвечает пошагово. Если не распознал — предлагает `/check`, `/diag`, `/logs` или `/status`.
- 🔒 **Whitelist** по `chat_id` (пустой = блок всех; `"any"` = пропустить всех для dev; `[123, 456]` = whitelist). По умолчанию безопасно закрыт.

Логи: `autrau-telegram-bot.out.log`.

## 🧹 Авто-очистка расшифровок

В настройках есть поле «Удалять расшифровки старше N дней»:

- `0` — не удалять никогда (по умолчанию)
- `N > 0` — файлы, расшифрованные **N или более дней назад**, удаляются автоматически

Фоновый цикл запускается при старте сервера и далее каждые **6 часов**. Кнопка «Очистить сейчас» в UI (или `POST /api/cleanup`) запускает очистку немедленно.

### ⭐ Избранные расшифровки

В карточке **«4. Расшифровки»** каждый файл можно пометить ★. Избранные расшифровки **никогда не удаляются** авто-очисткой, даже если подходят по возрасту (правило «старше N дней» для них не применяется). Снимите ★ — файл снова попадает под штатное удаление при следующей проверке.

### 🗑 Управление файлами расшифровок

В карточке **«4. Расшифровки»**:

- **галочка** у каждого файла (или клик по строке) — выбранные строки подсвечиваются, появляется плашка «🗑 Удалить выбранные (N)»;
- перед удалением — **подтверждение со списком имён** (случайно удалить нельзя); удаление также чистит список избранного;
- кнопка **«🗂 Открыть папку с файлами»** открывает `data/transcripts/` в проводнике, путь к папке показан в UI;
- отдельная корзина 🗑 есть у каждого файла.

Планы по развитию (Telegram-бот, экспорт SRT/VTT, серверный деплой и другое) — в [docs/ROADMAP.md](docs/ROADMAP.md).

## 🛠 Структура

```
autrau/
├── server.py              # FastAPI — API + раздача UI (единственный процесс)
├── index.html             # Web UI (без сборщиков)
├── autrau/                # package shim (v1.5.7): `python -m autrau` → server.py
│   ├── __init__.py         # version
│   ├── __main__.py         # запускает server.py
│   └── cli.py              # re-export tools.cli (`python -m autrau.cli`)
├── providers/
│   ├── base.py            # Provider ABC + реестр (registry)
│   ├── faster_whisper.py  # CTranslate2 (по умолчанию)
│   ├── whisper_cpp.py     # pywhispercpp
│   ├── parakeet.py        # NVIDIA NeMo
│   └── parakeet_onnx.py   # Parakeet v3 через ONNX/DirectML (без CUDA)
├── tools/
│   ├── config.py          # persistent user config (data/config.json)
│   ├── check.py           # диагностика (python -m tools.check)
│   ├── update.py          # self + model update (python -m tools.update)
│   ├── update_state.py    # persistent state для auto-update (v1.5.8)
│   ├── cleanup.py         # авто-очистка расшифровок + sidecar .segments.json
│   ├── translation.py     # провайдеры перевода (Argos/LibreTranslate/MiniMax)
│   ├── cli.py             # CLI: transcribe, batch, providers, models, status, health
│   ├── yt_dlp.py          # YouTube/Vimeo/etc → аудио (v1.5.7)
│   ├── system_audio.py    # WASAPI loopback — захват системного звука (v1.5.7)
│   ├── exports.py         # SRT/VTT/JSON/TXT форматтеры из segments (v1.5.6)
│   ├── telegram_bot.py    # Telegram agent bot (v1.7): голосовые/аудио/команды/FAQ
│   └── update_state.py    # persistent state для auto-update (v1.5.8)
├── data/                  # локальные данные (в .gitignore)
│   ├── config.json        # конфигурация
│   ├── update_state.json  # v1.5.8 — last_check / available / dismissed_version
│   ├── transcripts/       # архив расшифровок (+ .segments.json sidecars)
│   ├── voice-memos/       # голосовые заметки (+ .segments.json sidecars)
│   └── models/            # скачанные модели whisper-cpp / parakeet
├── docs/                  # документация
├── tests/                 # локальные тесты (gitignored)
├── start.bat              # 1-click запуск (Windows)
├── update.bat             # self-update (Windows)
├── start_telegram_bot.bat # 1-click запуск Telegram agent bot (v1.7, opt-in)

# Sibling project (отдельный репо):
# https://github.com/crosspostly/autrau-desktop (v1.6.0 Electron MVP)
├── publish.bat            # публикация в GitHub
├── requirements.txt
├── requirements-parakeet.txt
├── .env.example
└── LICENSE                # MIT
```

## ⚙️ Конфигурация

Через UI или `data/config.json`:

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

Полное описание всех ключей и переменных окружения — в [docs/CONFIGURATION.md](docs/CONFIGURATION.md).

## 🧠 Про провайдеров

### Faster-Whisper (по умолчанию) — 15 моделей
- **Когда выбрать:** универсальный. CPU+GPU, многоязычный (ru, en, de, fr, es, ...), стабильный.
- **Установка:** уже в `requirements.txt` (`faster-whisper`).
- **Модели:** `tiny`, `tiny.en`, `base`, `base.en`, `small`, `small.en`, `medium`, `medium.en`, `large-v1`, `large-v2`, `large-v3`, `large-v3-turbo` (быстрее large-v3), `distil-large-v3`, `distil-medium.en`, `distil-small.en` (EN-only).
- **Откуда:** `huggingface.co/Systran/faster-whisper-*` (+ `deepdml/...-turbo-ct2`).

### Whisper.cpp — 5 моделей
- **Когда выбрать:** слабый CPU / мало RAM. Без PyTorch, нативные биндинги.
- **Установка:** `pip install pywhispercpp`.
- **Модели:** `tiny`, `base`, `small`, `medium`, `large-v3` (ggml-формат).
- **Откуда:** `huggingface.co/ggerganov/whisper.cpp` → `ggml-*.bin`.

### Parakeet TDT v3 — 2 модели
- **Когда выбрать:** максимальная точность, NVIDIA RTX/A100/H100.
- **Установка:** `pip install -U nemo_toolkit[asr]` (тяжёлая: PyTorch + CUDA).
- **Модели:** `parakeet-tdt-0.6b-v3` (25 европейских языков, включая русский), `parakeet-tdt-0.6b-v2` (English-only).
- **Откуда:** `huggingface.co/nvidia/parakeet-tdt-0.6b-v3`.
<!-- VERIFY: Лицензия модели Parakeet — CC BY 4.0 (коммерческое использование разрешено) -->

### Parakeet v3 (ONNX/DirectML) — 1 модель
- **Когда выбрать:** тот же SOTA, но без NVIDIA: ускоряется через DirectX (DirectML) на **любом** GPU (AMD/Intel/NVIDIA) или работает на CPU.
- **Установка:** `pip install onnx-asr[hub] onnxruntime-directml` (лёгкая, без PyTorch/NeMo).
- **Модели:** `parakeet-tdt-0.6b-v3` — мультиязычная (25 языков, включая русский), int8-квантование (~640 МБ).
- **Откуда:** `huggingface.co/istupakov/parakeet-tdt-0.6b-v3-onnx` (ONNX-экспорт, CC BY 4.0).

## 🔌 HTTP API

| Метод | Путь | Описание |
|---|---|---|
| `GET` | `/` | Web UI |
| `GET` | `/docs` | **Swagger UI** (auto-generated OpenAPI) |
| `GET` | `/openapi.json` | OpenAPI schema (JSON) |
| `GET` | `/health` | статус сервера |
| `GET` | `/api/providers` | провайдеры + модели + активные |
| `GET` | `/api/config` | текущая конфигурация |
| `POST` | `/api/config` | обновить конфигурацию |
| `POST` | `/api/cleanup` | очистить расшифровки старше N дней |
| `GET` | `/api/transcripts` | список расшифровок + флаги избранного + `has_translation` |
| `GET` | `/api/transcripts/{name}` | скачать/открыть один `.txt` |
| `GET` | `/api/transcripts/{name}/export?format=srt\|vtt\|json\|txt` | **v1.5.6** экспорт с таймкодами |
| `POST` | `/api/favorites` | пометить/снять избранное (защита от авто-очистки) |
| `GET/DELETE` | `/api/voice-memos` | список/удаление голосовых заметок (`data/voice-memos/`) |
| `POST` | `/api/voice/{start,chunk,stop}` | запись голоса (MediaRecorder → ffmpeg → транскрипция) |
| `POST` | `/api/translate` | перевести текст через argos/libretranslate/minimax |
| `GET` | `/api/translate/providers` | статус каждого провайдера перевода |
| `POST` | `/api/translate/install-argos` | установить Argos + en_ru/ru_en модели в фоне |
| `GET` | `/api/updates` | проверка обновлений (`?stream=1` — SSE) |
| `POST` | `/api/updates/app` | self-update (git pull + pip upgrade) — DEPRECATED → use `/api/updates/apply` |
| `GET` | `/api/updates/state` | **v1.5.8** persistent state + should_notify + auto_update_enabled |
| `POST` | `/api/updates/check-now` | **v1.5.8** force check (обновляет state) |
| `POST` | `/api/updates/dismiss` | **v1.5.8** dismiss banner для текущей latest_version |
| `POST` | `/api/updates/apply` | **v1.5.8** apply update (git pull + pip upgrade; restart если `auto_update_app=true`) |
| `GET` | `/api/yt-dlp/info?url=...` | **v1.5.7** метаданные URL (title/duration/thumbnail) |
| `POST` | `/api/yt-dlp` | **v1.5.7** URL → аудио → транскрипция (SSE) |
| `GET` | `/api/system-audio/devices` | **v1.5.7** список loopback-устройств |
| `POST` | `/api/system-audio/start` | **v1.5.7** начать захват системного звука |
| `POST` | `/api/system-audio/stop` | **v1.5.7** стоп + транскрипция (SSE) |
| `POST` | `/api/model/download` | скачать модель (SSE) |
| `GET` | `/api/model/check` | проверить обновление одной модели |
| `POST` | `/api/provider/load` | вручную прогреть модель в память (UI сам лениво грузит при первой расшифровке) |
| `POST` | `/api/provider/install` | pip install провайдера |
| `POST` | `/transcribe` | транскрибация (SSE-поток) |

`POST /transcribe` принимает `multipart/form-data`: `file`, `language` (`ru|en|…|auto`), опционально `provider`, `model`, `device`. Ответ — Server-Sent Events:

```
data: {"type":"progress","percent":12,"payload":{"start":0,"end":3.2,"text":"..."}}
data: {"type":"done","percent":100,"payload":{"text":"...","segments":[...],"info":{...}}}
```

Неизвестный провайдер → `404` (со списком доступных); провайдер не установлен → `412`. Полная документация — в [docs/API.md](docs/API.md).

## 🚀 Публикация в GitHub

```powershell
publish.bat <your-github-username>
```

Скрипт: `git init` → создаёт репозиторий через `gh` CLI (или даёт ссылку на ручное создание) → initial commit → push в `origin/main`.

## 🛠 Устранение проблем

| Проблема | Решение |
|---|---|
| `ffmpeg not found` | `winget install Gyan.FFmpeg` и перезапустить терминал |
| Parakeet (NeMo) не ставится | Нужен NVIDIA GPU + CUDA 12+. Проверка: `nvidia-smi`. Без NVIDIA используйте **Parakeet v3 (ONNX/DirectML)** — работает на любом GPU/CPU |
| `faster-whisper` ошибка импорта | Обновите pip: `python -m pip install -U pip` |
| UI не обновляется | `Ctrl+F5` (hard reload) |
| `git pull failed` | Есть локальные изменения: `git stash` → `update.bat` → `git stash pop` |
| CORS ошибка | Откройте UI по `http://127.0.0.1:8000/`, не двойным кликом по html-файлу |

## 🤝 Вклад в проект

См. [CONTRIBUTING.md](CONTRIBUTING.md) — настройка окружения, стиль кода, правила PR.

## 📝 Лицензия

MIT — код Autrau. Модели — по своим лицензиям: Faster-Whisper (MIT), Whisper.cpp (MIT), Parakeet v3 (CC BY 4.0).
