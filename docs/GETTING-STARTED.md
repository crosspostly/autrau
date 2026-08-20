<!-- generated-by: gsd-doc-writer -->
# Быстрый старт с Autrau

## Предварительные требования

- **Python ≥ 3.10** ([python.org](https://www.python.org/downloads/)) — при установке на Windows отметьте **Add Python to PATH**
- **ffmpeg** — нужен faster-whisper для `mp3`/`m4a`/`ogg`/`flac`/`webm` (Windows: `winget install Gyan.FFmpeg`, затем перезапустите терминал)
- **git** — для самообновления (Windows: `winget install Git.Git`; macOS: `brew install git`)
- **Диск**: ~1–3 ГБ на модель (модели качаются по требованию из Hugging Face). ~336 МБ дополнительно если ставите Argos Translate для офлайн-перевода.
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

# v1.5.7: URL → транскрипция (YouTube / Vimeo / X / ~1500 сайтов)
pip install yt-dlp

# v1.5.7: захват системного звука (loopback, Windows WASAPI / macOS / Linux Pulse)
pip install soundcard
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
| `yt-dlp не установлен` (URL → транскрипция) | `pip install yt-dlp` (только в venv сервера) |
| `soundcard не установлен` (системный звук) | `pip install soundcard` (нужен CFFI; на Windows обычно работает из коробки) |
| `Нет loopback-устройств` | Windows: включите Stereo Mix в настройках звука или используйте наушники/колонки с WASAPI loopback |

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

## CLI-инструмент (v1.5.7+)

После установки зависимостей и старта сервера можно работать из терминала:

```bash
# Транскрибировать один файл → stdout
python -m autrau.cli transcribe interview.mp3

# С указанием языка и выходного файла
python -m autrau.cli transcribe voice.webm --language en --output out.txt

# Экспорт сразу в SRT / VTT / JSON
python -m autrau.cli transcribe podcast.mp3 --output subs.srt --format srt

# Пакетная обработка директории
python -m autrau.cli batch ./audio/ --pattern "*.{mp3,wav}" --output ./out/

# Список провайдеров и активный
python -m autrau.cli providers

# Список моделей конкретного провайдера
python -m autrau.cli models --provider whisper-cpp

# Статус сервера + конфигурация
python -m autrau.cli status

# Быстрая проверка доступности
python -m autrau.cli health
```

CLI работает через HTTP API запущенного сервера. Если сервер на другом хосте/порту:

```powershell
$env:AUTRAU_API = "http://192.168.1.10:8000"
python -m autrau.cli status
```

Подробности — в [API.md](API.md) (раздел `/api/transcripts/{name}/export` и `/transcribe`).

## URL → транскрипция (v1.5.7+)

`yt-dlp` обёртка для YouTube, Vimeo, X/Twitter, Twitch, SoundCloud и ещё ~1500 сайтов. Установите зависимость (`pip install yt-dlp`), затем используйте UI (раскрывающийся блок «🔗 URL → транскрипция» с полем URL и кнопкой «Превью»/«Транскрибировать») или API:

```bash
# Метаданные (без скачивания)
curl "http://127.0.0.1:8000/api/yt-dlp/info?url=https://www.youtube.com/watch?v=dQw4w9WgXcQ"

# Транскрибировать видео (SSE stream)
curl -N -X POST http://127.0.0.1:8000/api/yt-dlp \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "language": "en"}'
```

Скачивается лучшее доступное аудио → конвертируется в WAV (FFmpegExtractAudio) → отправляется в тот же пайплайн что и `/transcribe`. Результат — обычный `.txt` + sidecar `.segments.json` в `data/transcripts/`.

## Системный звук / loopback (v1.5.7+)

Захват того, что играет в колонках/наушниках — для транскрибации подкастов, видео, созвонов без отдельного скачивания.

```bash
# Список loopback-устройств (Windows WASAPI / macOS / Linux PulseAudio)
curl http://127.0.0.1:8000/api/system-audio/devices

# Начать запись
curl -X POST http://127.0.0.1:8000/api/system-audio/start \
  -H "Content-Type: application/json" \
  -d '{"device_id": 0}'

# ... подождать нужное время ...

# Остановить + транскрибировать (SSE)
curl -N -X POST http://127.0.0.1:8000/api/system-audio/stop \
  -H "Content-Type: application/json" \
  -d '{"save_to": "transcripts"}'
```

Только **одна** активная запись одновременно (single instance lock в `server.py`). Зависимость: `pip install soundcard`.

В UI — секция «🔊 Системный звук» в правой колонке: dropdown со списком устройств, кнопки «Начать запись»/«Остановить».

## Экспорт субтитров (v1.5.6+)

В карточке результата — кнопка «📤 Экспорт ▾» с dropdown SRT / VTT / JSON / TXT. Использует sidecar `<stem>.segments.json` для конвертации без ре-транскрибации. Старые расшифровки без sidecar экспортируются в «плоский» формат (один сегмент).

```bash
# Скачать SRT
curl -OJ "http://127.0.0.1:8000/api/transcripts/2026-08-19_voice-123.mp3.txt/export?format=srt"

# VTT для HTML5 video
curl "http://127.0.0.1:8000/api/transcripts/2026-08-19_voice-123.mp3.txt/export?format=vtt"

# JSON с метаданными (language, provider, model, duration, segments)
curl "http://127.0.0.1:8000/api/transcripts/2026-08-19_voice-123.mp3.txt/export?format=json"
```

## Авто-обновления (v1.5.8+)

Сервер проверяет обновления в фоне каждые `update_check_interval_hours` (по умолчанию 6 часов). При наличии — UI показывает баннер «🆕 Доступно обновление: `<short_sha>`» с кнопками «Обновить» и «Позже».

- `auto_update_app: false` (default) — кнопка «Обновить» применяет обновление вручную; сервер перезапускается через `os.execv`, UI ловит `/health` и перезагружается.
- `auto_update_app: true` — background scheduler сам применяет обновление и перезапускает сервер (opt-in, для always-on установок).

Кнопка «🔄 Проверить» в шестерёнке → `POST /api/updates/check-now` — принудительная проверка.
