# 🎙️ Autrau

**Локальный мульти-провайдерный транскрибатор аудио. Без облака, без интернета, с авто-обновлениями.**

Переводит речь из аудиофайлов (`mp3`, `wav`, `m4a`, `ogg`, `flac`, `webm`) в текст. Поддерживает три бэкенда на выбор:

| Провайдер | Что внутри | Скорость | Точность | RAM | GPU |
|---|---|---|---|---|---|
| **faster-whisper** *(по умолчанию)* | CTranslate2 | ⚡⚡ | ★★★★ | 2 ГБ | опц. |
| **whisper.cpp** | pywhispercpp (C++ биндинги) | ⚡⚡⚡ | ★★★★ | 1 ГБ | нет |
| **Parakeet TDT v3** | NVIDIA NeMo | ⚡⚡⚡ | ★★★★★ | 4 ГБ | **да** |

Все три качают модели напрямую с официальных реестров:

- `huggingface.co/Systran/faster-whisper-*` — Faster-Whisper
- `huggingface.co/ggerganov/whisper.cpp` — Whisper.cpp (ggml-*.bin)
- `huggingface.co/nvidia/parakeet-tdt-0.6b-v3` — Parakeet v3 (SOTA 2025-2026)

---

## ⚡ Запуск в 1 клик (Windows)

1. Установите [Python 3.10+](https://www.python.org/downloads/) (при установке — галка **Add Python to PATH**)
2. Двойной клик по **`start.bat`**

Скрипт сам:
- Создаст venv (если нет)
- Поставит `fastapi`, `uvicorn`, `faster-whisper`
- Проверит Python, ffmpeg, git
- Покажет состояние провайдеров
- Запустит сервер и откроет http://127.0.0.1:8000/

Хотите другие провайдеры? В UI нажмите «⬇ Установить провайдер» — `pywhispercpp` или `nemo_toolkit[asr]` поставятся автоматически.

---

## 📦 Установка вручную

```powershell
git clone https://github.com/<you>/autrau.git
cd autrau
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python server.py
```

Опциональные провайдеры (по желанию):

```powershell
# whisper.cpp — без PyTorch, лёгкий
pip install pywhispercpp

# Parakeet v3 — нужен NVIDIA GPU + CUDA
pip install -r requirements-parakeet.txt
```

---

## 🔄 Обновления

```powershell
# Обновить приложение (git pull + pip upgrade) + проверить модели
update.bat

# Только проверить, что нового
update.bat     # (без изменений в файлах)
```

В UI: вкладка **🔄 Обновления** показывает:
- 📦 новые коммиты в GitHub
- 🧠 новые версии моделей на HuggingFace

Кнопка **⬇ Обновить приложение** делает `git pull --ff-only` + `pip install --upgrade`.

---

## 🛠 Структура

```
autrau/
├── server.py              # FastAPI — multi-provider API
├── index.html             # UI (без сборщиков)
├── providers/
│   ├── base.py            # абстракция + реестр
│   ├── faster_whisper.py  # CTranslate2 (по умолчанию)
│   ├── whisper_cpp.py     # pywhispercpp
│   └── parakeet.py        # NVIDIA NeMo
├── tools/
│   ├── config.py          # persistent user config
│   ├── check.py           # диагностика
│   └── update.py          # self + model update
├── data/                  # локальные данные (в .gitignore)
├── start.bat              # 1-click запуск
├── update.bat             # self-update
├── publish.bat            # публикация в GitHub
├── requirements.txt
├── requirements-parakeet.txt
├── .env.example
└── README.md
```

---

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
  "auto_update_app": false
}
```

Через env-переменные (`.env`):

```ini
AUTRAU_HOST=127.0.0.1
AUTRAU_PORT=8000
AUTRAU_PROVIDER=faster-whisper
AUTRAU_MODEL=small
AUTRAU_DEVICE=cpu
```

---

## 🧠 Про провайдеров

### Faster-Whisper (по умолчанию)
- **Когда выбрать:** универсальный. CPU+GPU, 99 языков, хорошая документация.
- **Зависимости:** `faster-whisper` (CTranslate2, уже в `requirements.txt`).
- **Модели:** `tiny`, `base`, `small`, `medium`, `large-v1/v2/v3`, `distil-large-v3`.
- **Где лежат модели:** `huggingface.co/Systran/faster-whisper-{size}` (HF API → `lastModified`).

### Whisper.cpp
- **Когда выбрать:** слабый CPU / мало RAM. Нет PyTorch, нативные биндинги.
- **Зависимости:** `pywhispercpp` (ставится через UI или `pip install pywhispercpp`).
- **Модели:** `tiny`, `base`, `small`, `medium`, `large-v3` (ggml-формат).
- **Где лежат:** `huggingface.co/ggerganov/whisper.cpp` → `ggml-*.bin` (HF API).

### Parakeet TDT v3
- **Когда выбрать:** SOTA 2025-2026, NVIDIA RTX/A100/H100. 25 европейских языков включая русский.
- **Зависимости:** `nemo_toolkit[asr]` + PyTorch CUDA (тяжёлая установка).
- **Модель:** одна — `nvidia/parakeet-tdt-0.6b-v3` (600 М параметров).
- **Где лежит:** `huggingface.co/nvidia/parakeet-tdt-0.6b-v3`.
- **Лицензия модели:** CC BY 4.0 (коммерческое использование ОК).

---

## 🔌 HTTP API (если нужна интеграция)

```http
GET  /api/providers          # список провайдеров и моделей
GET  /api/config             # текущая конфигурация
POST /api/config             # {provider, model, device, language, ...}
POST /api/provider/load      # загрузить модель в память
POST /api/provider/install   # pip install провайдера
GET  /api/updates            # проверить обновления
POST /api/updates/app        # git pull + pip upgrade
POST /api/model/download     # SSE-стрим скачивания модели
POST /transcribe             # SSE-стрим транскрибации
```

`POST /transcribe` принимает `multipart/form-data`:
- `file` — аудио
- `language` — `ru` | `en` | `de` | ... | `auto`
- `provider`, `model`, `device` — переопределение дефолта

Ответ — поток Server-Sent Events:
```
data: {"type":"progress","percent":12,"payload":{"start":0,"end":3.2,"text":"..."}}
data: {"type":"progress","percent":27,"payload":{"start":3.2,"end":7.1,"text":"..."}}
data: {"type":"done","percent":100,"payload":{"text":"...","segments":[...],"info":{...}}}
```

---

## 🚀 Публикация в GitHub

```powershell
publish.bat <your-github-username>
```

Скрипт:
1. `git init` (если нет)
2. Создаст репо `autrau` через `gh` CLI (если установлен) ИЛИ даст ссылку на ручное создание
3. Сделает initial commit
4. Запушит в `origin/main`

---

## 🛠 Устранение проблем

| Проблема | Решение |
|---|---|
| `ffmpeg not found` | `winget install Gyan.FFmpeg` и перезапустить терминал |
| Parakeet не ставится | Нужен NVIDIA GPU + CUDA 12+. Проверка: `nvidia-smi` |
| `faster-whisper` ошибка импорта | Обновите pip: `python -m pip install -U pip` |
| UI не обновляется | `Ctrl+F5` (hard reload) |
| `git pull failed` | Есть локальные изменения: `git stash` → `update.bat` → `git stash pop` |
| CORS ошибка | Откройте UI по `http://127.0.0.1:8000/`, не двойным кликом по html |

---

## 📝 Лицензия

MIT — код Autrau.  
Модели — по各自的 лицензиям: Faster-Whisper (MIT), Whisper.cpp (MIT), Parakeet v3 (CC BY 4.0).
