<!-- generated-by: gsd-doc-writer -->
# Быстрый старт с Autrau

## Предварительные требования

- **Python ≥ 3.10** ([python.org](https://www.python.org/downloads/)) — при установке на Windows отметьте **Add Python to PATH**
- **ffmpeg** — нужен faster-whisper для `mp3`/`m4a`/`ogg`/`flac`/`webm` (Windows: `winget install Gyan.FFmpeg`, затем перезапустите терминал)
- **git** — для самообновления (Windows: `winget install Git.Git`; macOS: `brew install git`)
- **Диск**: ~1–3 ГБ на модель (модели качаются по требованию из Hugging Face)
- **RAM**: 1 ГБ (whisper.cpp) – 4 ГБ (Parakeet v3) в зависимости от провайдера

Операционные системы: Windows (основная поддержка, есть `start.bat`), macOS и Linux работают через `python server.py`.

## Установка

```bash
git clone https://github.com/crosspostly/autrau.git
cd autrau
python -m venv .venv
# Windows (PowerShell):
.\.venv\Scripts\Activate.ps1
# macOS / Linux:
source .venv/bin/activate

pip install -r requirements.txt
```

По умолчанию ставится провайдер **faster-whisper** (в `requirements.txt`). Остальные — по желанию:

```bash
# whisper.cpp (CPU-only, лёгкий)
pip install pywhispercpp

# Parakeet v3 (NVIDIA GPU + CUDA, тяжёлая установка ~3–5 ГБ)
pip install -r requirements-parakeet.txt
```

## Первый запуск

```bash
python server.py
```

Откройте **http://127.0.0.1:8000/** — закиньте аудиофайл в окно и нажмите «Транскрибировать». Перед первой транскрибацией скачайте модель: вкладка провайдера → «⬇ Скачать» (или `POST /api/model/download`). Если модель не скачана, сервер вернёт `404` «Модель не скачана» — автозагрузки при транскрибации нет.

На Windows вместо ручных шагов можно просто запустить **`start.bat`** — он сам создаст venv, поставит зависимости, проверит окружение и откроет браузер.

## Частые проблемы при первом запуске

| Проблема | Решение |
|---|---|
| `ffmpeg not found` | `winget install Gyan.FFmpeg` (Windows) / `brew install ffmpeg` (macOS); перезапустите терминал |
| Ошибка `412` при транскрибации | Выбранный провайдер не установлен — поставьте его из UI («Установить провайдер») или `pip install ...` |
| Ошибка `404` «Модель не скачана» | Скачайте модель: UI → вкладка провайдера → «⬇ Скачать», или `POST /api/model/download` |
| Порт 8000 занят | `$env:AUTRAU_PORT = "8001"` перед `python server.py` (см. [CONFIGURATION.md](CONFIGURATION.md)) |
| UI не открывается / CORS | Открывайте именно `http://127.0.0.1:8000/`, а не файл `index.html` двойным кликом |
| Медленная проверка обновлений при старте | `check_updates_on_start: false` в `data/config.json` |
| Ошибка установки на macOS/Apple Silicon | Для whisper.cpp и faster-whisper есть ARM-колёса; убедитесь, что Python установлен через Homebrew / python.org, а не устаревший системный |

## Дальнейшие шаги

- [CONFIGURATION.md](CONFIGURATION.md) — все настройки и переменные окружения
- [API.md](API.md) — полное описание HTTP-эндпоинтов
- [DEVELOPMENT.md](DEVELOPMENT.md) — как устроена разработка и как добавить свой провайдер
- [TESTING.md](TESTING.md) — как проверять изменения
- [ARCHITECTURE.md](ARCHITECTURE.md) — общая схема системы

## Автоперевод на английский (опционально, v1.5+)

По умолчанию перевод **выключен** (`translate_to_en: false`). Чтобы включить — откройте шестерёнку → «3.5 🌐 Перевод на английский» → поставьте галочку + выберите провайдера + 💾 Сохранить.

**Рекомендуемый провайдер: Argos Translate (локально, ~336 МБ en↔ru, без облака).**

Установка одной кнопкой в UI: «📥 Установить Argos» в той же секции. Установка идёт в фоне (pip + скачивание моделей с `argos-net.com`); после — `argos.available=true` в `/api/translate/providers`, badge `✓ Argos` в hero.

Установка вручную (если UI-кнопка не работает):

```bash
# В venv сервера:
.\.venv\Scripts\python.exe -m pip install argostranslate langdetect
# Скачать обе модели en↔ru (~336 МБ, общая папка ~/local/share/argos-translate/packages/):
.\.venv\Scripts\python.exe -c "from argostranslate import package; package.update_package_index(); [p.install() for p in package.get_available_packages() if p.code in ('translate-en_ru', 'translate-ru_en')]"
# Перезапустить сервер (чтобы Python увидел новый пакет)
```

⚠️ Публичные LibreTranslate инстансы (`libretranslate.com` и др.) мертвы в 2025 (502/403/404). Используйте Argos (локально) или MiniMax (платный API, ключ в `~/.minimax/auth.json`).
