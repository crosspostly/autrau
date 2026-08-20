<!-- generated-by: gsd-doc-writer -->
# Разработка Autrau

## Локальная настройка окружения

```bash
git clone https://github.com/crosspostly/autrau.git
cd autrau
python -m venv .venv
# Windows:
.\.venv\Scripts\Activate.ps1
# macOS / Linux:
source .venv/bin/activate

pip install -r requirements.txt
```

Специального набора dev-зависимостей нет — используется тот же `requirements.txt` (FastAPI, uvicorn, python-multipart, huggingface-hub, faster-whisper). Для работы над другими провайдерами / функциями:

```bash
pip install pywhispercpp            # whisper.cpp
pip install -r requirements-parakeet.txt   # Parakeet v3 (NVIDIA GPU + CUDA)
pip install argostranslate langdetect      # Translation: Argos (v1.5.1+)
pip install yt-dlp                  # v1.5.7: URL → транскрипция
pip install soundcard               # v1.5.7: захват системного звука
pip install "python-telegram-bot>=20.0,<22.0"   # v1.7: Telegram agent bot (opt-in)
```

## Команды

| Команда | Что делает |
|---|---|
| `python server.py` | Запуск сервера (UI + API) на `http://127.0.0.1:8000/` |
| `python -m autrau` | То же самое через package shim (v1.5.7+) |
| `python -m autrau.cli <sub>` | CLI-инструмент (transcribe, batch, providers, models, status, health) |
| `python -m tools.telegram_bot` | **v1.7**: Telegram agent bot (нужен `telegram_bot_token` в config) |
| `python -m tools.check` | Полная диагностика: Python, ffmpeg, зависимости, git, провайдеры, обновления |
| `python -m tools.update --check` | Только проверить обновления (приложение + модели) |
| `python -m tools.update --app` | Обновить приложение: `git pull --ff-only` + `pip install --upgrade -r requirements.txt` |
| `python -m compileall -q providers tools server.py autrau` | Компиляционная проверка всех Python-файлов (то же, что гоняет CI) |
| `python -m pytest tests/ -v` | Прогон unit-тестов (v1.5.8+: `tests/test_update_state.py` — 10/10 pass) |
| `python tests/test_update_state.py` | Тот же тест, но без pytest (запасной вариант) |
| `python -c "from tools import translation; tr.translate('hello', 'ru', provider_name='minimax')"` | Тест провайдера перевода напрямую (если есть MiniMax ключ) |

## Стиль кода

- Форматтер/линтер **не настроены** (нет `.editorconfig`, `.ruff.toml`, `pyproject.toml` и т.п.) — придерживайтесь PEP 8 и стиля соседних файлов.
- **Python ≥ 3.10** (используются `X | None`, `dict[str, Any]`, `Path`).
- **Стандартная библиотека в приоритете** — тяжёлые зависимости только там, где они действительно нужны (модели, HTTP).
- Пользовательские сообщения в UI и логах — на русском языке.
- Обязательное требование: `python -m compileall -q providers tools server.py autrau` и JSON-валидность всех `.json` файлов — это проверяет CI.
- Новая функциональность должна быть обратимой по конфигу (дефолты в `tools/config.py:19`).

## Паттерны

### Lazy-load провайдера в каждом endpoint

Провайдер загружается в память **один раз** под `asyncio.Lock`. Endpoint'ы, которые дёргают `p.transcribe()` напрямую (не через `/transcribe`, например `/api/system-audio/stop`, `/api/yt-dlp`), должны вручную проверять и инициализировать:

```python
# server.py (v1.5.7+)
p = registry.get(provider)
if p is None:
    raise HTTPException(404, ...)
if _loaded_provider != provider or _loaded_model != model:
    # sync load через run_in_executor
    await loop.run_in_executor(None, lambda: p.load(model, device))
    _loaded_provider, _loaded_model, _loaded_device = provider, model, device
```

Не надейтесь на `await _lazy_load()` — оно есть в `/transcribe`, но в каждом новом endpoint нужно копировать проверку.

### Atomic write для persistent state

`tools/update_state.py` использует `tempfile.mkstemp` + `os.replace` — атомарная запись без partial files:

```python
def _atomic_write(path: Path, data: dict) -> None:
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)
    except Exception:
        try: os.unlink(tmp_path)
        except OSError: pass
        raise
```

Используйте тот же паттерн для любого нового persistent state.

### Background tasks в lifespan

С v1.5.8 новый background scheduler добавляется через `lifespan` контекст-менеджер в FastAPI:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
    _init_config()
    _init_update_state()
    update_task = asyncio.create_task(_update_scheduler())
    yield
    # shutdown
    update_task.cancel()
    try:
        await update_task
    except asyncio.CancelledError:
        pass
```

### SSE для долгих операций

Все endpoint'ы с прогрессом (`/transcribe`, `/api/model/download`, `/api/updates?stream=1`, `/api/yt-dlp`, `/api/system-audio/stop`) используют SSE-стрим через `asyncio.Queue` + `EventSourceResponse` или прямой `StreamingResponse(media_type="text/event-stream")`. Формат события — `{type: progress|done|error, percent: 0-100, payload: {...}}`, сериализуется как `data: {json}\n\n`.

### Sidecar-файлы для метаданных

С v1.5.6 сегменты сохраняются как `<stem>.segments.json` рядом с `<stem>.txt` (см. `tools/cleanup.py:save_transcript(..., segments=...)`). Это позволяет re-export в SRT/VTT/JSON без ре-транскрибации.

Формат sidecar:
```json
{
  "version": 1,
  "transcript": "2026-08-19_voice-123.mp3.txt",
  "language": "ru",
  "provider": "parakeet-onnx",
  "model": "parakeet-tdt-0.6b-v3",
  "duration": 6.014,
  "segments": [
    {"start": 0.098, "end": 0.574, "text": "Привет."},
    ...
  ]
}
```

Если новая функция пишет транскрипт — принимайте `segments` параметр и пишите sidecar через `path.with_name(path.stem + ".segments.json")`.

## Ветки

- Основная ветка — `main` (CI запускается на push/PR в `main`).
- Соглашение об именовании веток не задокументировано — используйте осмысленные имена (`fix/...`, `feat/...`, `docs/...`).
- Публикация нового репозитория — `publish.bat <username>` (init + initial commit + push).

## Процесс PR

1. Сделайте форк (или ветку) и внесите изменения.
2. Проверьте локально: `python -m compileall -q providers tools server.py autrau`, запустите сервер и прогоните smoke-тест (`/health`, `/api/providers`, транскрибацию тестового файла). Если добавили unit-тесты — `python -m pytest tests/ -v`.
3. Создайте pull request в `main` с описанием: что меняется, зачем, как проверить.
4. CI (`.github/workflows/ci.yml`) автоматически проверит компиляцию Python и валидность JSON — дождитесь зелёного статуса.
5. Изменения API и конфигурации — с обратной совместимостью (пример: `/api/updates` по умолчанию отдаёт JSON, `?stream=1` — SSE; `/api/updates/app` помечен DEPRECATED в пользу `/api/updates/apply`).

## Как добавить новый провайдер

1. Создайте `providers/my_provider.py` — подкласс `Provider` (см. `providers/base.py:53`): реализуйте `is_available`, `install`, `list_models`, `is_model_downloaded`, `download_model`, `check_model_update`, `load`, `transcribe`.
2. Заполните `ProviderInfo` (название, модели, языки, hint установки).
3. Зарегистрируйте в `providers/__init__.py` (порядок = порядок в UI).
4. Готово — UI и API подхватят провайдера без изменений; не забудьте обновить списки моделей в доках.

## Как добавить новый провайдер перевода

1. Создайте подкласс `TranslationProvider` в `tools/translation.py` (см. ABC: `name: str`, `is_available() -> (bool, str)`, `translate(text, source, target) -> str`).
2. Зарегистрируйте в `get_provider(name)` (рядом с существующими `minimax` / `libretranslate` / `argos`).
3. При необходимости добавьте конфиг-ключ в `tools/config.py:DEFAULTS` (например, `my_provider_url`).
4. Готово — UI подхватит провайдера через `/api/translate/providers` (для отображения badge) + `/api/translate` (для перевода).

Модели Argos Translate скачиваются с `https://argos-net.com/v1/<...>.argosmodel` (НЕ `argosopentech.com` — мёртв с 2024) по индексу `https://raw.githubusercontent.com/argosopentech/argospm-index/main/`.

## Как добавить новый формат экспорта

1. Добавьте форматтер в `tools/exports.py` (по образцу `to_srt` / `to_vtt` / `to_json_segments`).
2. Расширьте `SUPPORTED_FORMATS = ("srt", "vtt", "json", "txt", "<new>")`.
3. Добавьте ветку в `export_transcript()` с правильным `media_type`.
4. В UI (`index.html`) — добавьте кнопку в `#exportMenu` dropdown.
5. Дока — обновите раздел «Экспорт субтитров» в `docs/GETTING-STARTED.md` и `docs/API.md`.

## CLI subcommand

Чтобы добавить новый subcommand в `python -m autrau.cli`:

1. В `tools/cli.py` — добавьте функцию `cmd_mycommand(args: argparse.Namespace) -> int` и зарегистрируйте через `sub.add_parser("mycommand", ...).set_defaults(func=cmd_mycommand)`.
2. Используйте `_http_get_json()` для GET-запросов и собирайте multipart вручную (см. `_build_multipart`) для POST.
3. Для streaming — парсите SSE через `_parse_sse_stream()`.

Подробности внутреннего устройства — в [ARCHITECTURE.md](ARCHITECTURE.md).
