<!-- generated-by: gsd-doc-writer -->
# 🎙️ Autrau

**Локальный мульти-провайдерный транскрибатор аудио. Без облака, без загрузки записей на чужие серверы.**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![CI](https://img.shields.io/github/actions/workflow/status/crosspostly/autrau/ci.yml?label=CI)](.github/workflows/ci.yml)

Переводит речь из аудио- и видеофайлов (`mp3`, `wav`, `m4a`, `ogg`, `flac`, `webm`, `mp4`, `mkv`, `mov`) в текст локально — у видео звук извлекается автоматически (нужен ffmpeg). Три бэкенда на выбор — 22 модели суммарно:

| Провайдер | Что внутри | Моделей | RAM | GPU | Особенности |
|---|---|---|---|---|---|
| **Faster-Whisper** *(по умолчанию)* | CTranslate2 | 15 | 2 ГБ | опц. | CPU и GPU, многоязычный |
| **Whisper.cpp** | pywhispercpp (C++ биндинги) | 5 | 1 ГБ | нет | Без PyTorch, очень лёгкий |
| **Parakeet TDT v3** | NVIDIA NeMo | 2 | 4 ГБ | **да** | SOTA 2025–2026, 25 европейских языков |
| **Parakeet v3 (ONNX/DirectML)** | onnx-asr + DirectML | 1 | 1.5 ГБ | любой GPU/CPU | Тот же SOTA без CUDA: DirectX на любом GPU |

Модели скачиваются напрямую с официальных реестров Hugging Face:
`Systran/faster-whisper-*`, `deepdml/faster-whisper-large-v3-turbo-ct2`, `ggerganov/whisper.cpp` (ggml-`*.bin`), `nvidia/parakeet-tdt-0.6b-v3`, `istupakov/parakeet-tdt-0.6b-v3-onnx` (int8, ~640 МБ).

---

## ✨ Возможности

- 🧠 **23 модели** — от `tiny` (75 МБ) до `large-v3` (2.9 ГБ) и дистиллированных EN-вариантов
- 📡 **SSE-прогресс** — и транскрибация, и проверка обновлений стримят прогресс в реальном времени
- 🔄 **Авто-обновления** — проверка новых коммитов приложения и новых версий моделей
- 🧹 **Авто-очистка расшифровок** — старые расшифровки удаляются автоматически по возрасту (или вручную)
- ⭐ **Избранное** — помеченные расшифровки никогда не удаляются авто-очисткой; снятие ярлыка снова включает их в штатное удаление
- 🗂 **Архив расшифровок** — каждая расшифровка сохраняется в `data/transcripts/`, со списком и метаданными в UI
- 🖥 **Web UI** — без сборщиков, один `index.html`; drag-and-drop, тёмная тема

---

## ⚡ Запуск в 1 клик (Windows)

1. Установите [Python 3.10+](https://www.python.org/downloads/) (при установке — галка **Add Python to PATH**)
2. Двойной клик по **`start.bat`**

Скрипт сам создаст venv, поставит зависимости, проверит Python/ffmpeg/git, покажет состояние провайдеров и запустит сервер: **http://127.0.0.1:8000/**.

Другие провайдеры ставятся из UI: кнопка «⬇ Установить провайдер» → `pywhispercpp` или `nemo_toolkit[asr]`.

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
```

## 🎧 Использование

1. Откройте **http://127.0.0.1:8000/** — закиньте аудиофайл в окно
2. Выберите провайдера/модель (или оставьте дефолт: `faster-whisper / small`)
3. Нажмите «Транскрибировать» — прогресс идёт по сегментам, в конце текст можно скопировать

Или через API:

```powershell
# Транскрибация (SSE-поток)
curl -N -F "file=@speech.mp3" -F "language=ru" http://127.0.0.1:8000/transcribe

# Список провайдеров и моделей
curl http://127.0.0.1:8000/api/providers

# Проверка обновлений приложения и моделей (SSE-прогресс)
curl -N "http://127.0.0.1:8000/api/updates?stream=1"
```

После транскрибации расшифровка автоматически сохраняется в `data/transcripts/` — файл `<дата>_<время>_<имя>.txt` с шапкой (файл, дата, модель, язык).

## 🔄 Обновления

```powershell
update.bat
```

- `git pull --ff-only` + `pip install --upgrade -r requirements.txt`
- Проверка новых версий моделей на Hugging Face

В UI вкладка **🔄 Обновления** показывает новые коммиты и новые версии моделей; `/api/updates?stream=1` стримит прогресс по каждой из 22 моделей. Кнопка «⬇ Обновить приложение» делает то же, что `update.bat`.

## 🧹 Авто-очистка расшифровок

В настройках есть поле «Удалять расшифровки старше N дней»:

- `0` — не удалять никогда (по умолчанию)
- `N > 0` — файлы, расшифрованные **N или более дней назад**, удаляются автоматически

Фоновый цикл запускается при старте сервера и далее каждые **6 часов**. Кнопка «Очистить сейчас» в UI (или `POST /api/cleanup`) запускает очистку немедленно.

### ⭐ Избранные расшифровки

В карточке **«4. Расшифровки»** каждый файл можно пометить ★. Избранные расшифровки **никогда не удаляются** авто-очисткой, даже если подходят по возрасту (правило «старше N дней» для них не применяется). Снимите ★ — файл снова попадает под штатное удаление при следующей проверке.

Планы по развитию (Telegram-бот, экспорт SRT/VTT, серверный деплой и другое) — в [docs/ROADMAP.md](docs/ROADMAP.md).

## 🛠 Структура

```
autrau/
├── server.py              # FastAPI — API + раздача UI (единственный процесс)
├── index.html             # Web UI (без сборщиков)
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
│   └── cleanup.py         # авто-очистка расшифровок
├── data/                  # локальные данные (в .gitignore)
│   ├── config.json        # конфигурация
│   ├── transcripts/       # архив расшифровок
│   └── models/            # скачанные модели whisper-cpp
├── docs/                  # документация
├── start.bat              # 1-click запуск (Windows)
├── update.bat             # self-update (Windows)
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
  "cleanup_after_days": 0
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
| `GET` | `/health` | статус сервера |
| `GET` | `/api/providers` | провайдеры + модели + активные |
| `GET` | `/api/config` | текущая конфигурация |
| `POST` | `/api/config` | обновить конфигурацию |
| `POST` | `/api/cleanup` | очистить расшифровки старше N дней |
| `GET` | `/api/transcripts` | список расшифровок + флаги избранного |
| `POST` | `/api/favorites` | пометить/снять избранное (защита от авто-очистки) |
| `GET` | `/api/updates` | проверка обновлений (`?stream=1` — SSE) |
| `POST` | `/api/updates/app` | self-update (git pull + pip upgrade) |
| `POST` | `/api/model/download` | скачать модель (SSE) |
| `GET` | `/api/model/check` | проверить обновление одной модели |
| `POST` | `/api/provider/load` | загрузить модель в память |
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
