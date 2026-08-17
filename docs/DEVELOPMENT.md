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

Специального набора dev-зависимостей нет — используется тот же `requirements.txt` (FastAPI, uvicorn, python-multipart, huggingface-hub, faster-whisper). Для работы над другими провайдерами:

```bash
pip install pywhispercpp            # whisper.cpp
pip install -r requirements-parakeet.txt   # Parakeet v3 (NVIDIA GPU + CUDA)
```

## Команды

| Команда | Что делает |
|---|---|
| `python server.py` | Запуск сервера (UI + API) на `http://127.0.0.1:8000/` |
| `python -m tools.check` | Полная диагностика: Python, ffmpeg, зависимости, git, провайдеры, обновления |
| `python -m tools.update --check` | Только проверить обновления (приложение + модели) |
| `python -m tools.update --app` | Обновить приложение: `git pull --ff-only` + `pip install --upgrade -r requirements.txt` |
| `python -m compileall -q providers tools server.py` | Компиляционная проверка всех Python-файлов (то же, что гоняет CI) |

## Стиль кода

- Форматтер/линтер **не настроены** (нет `.editorconfig`, `.ruff.toml`, `pyproject.toml` и т.п.) — придерживайтесь PEP 8 и стиля соседних файлов.
- **Python ≥ 3.10** (используются `X | None`, `dict[str, Any]`, `Path`).
- **Стандартная библиотека в приоритете** — тяжёлые зависимости только там, где они действительно нужны (модели, HTTP).
- Пользовательские сообщения в UI и логах — на русском языке.
- Обязательное требование: `python -m compileall -q providers tools server.py` и JSON-валидность всех `.json` файлов — это проверяет CI.
- Новая функциональность должна быть обратимой по конфигу (дефолты в `tools/config.py:19`).

## Ветки

- Основная ветка — `main` (CI запускается на push/PR в `main`).
- Соглашение об именовании веток не задокументировано — используйте осмысленные имена (`fix/...`, `feat/...`, `docs/...`).
- Публикация нового репозитория — `publish.bat <username>` (init + initial commit + push).

## Процесс PR

1. Сделайте форк (или ветку) и внесите изменения.
2. Проверьте локально: `python -m compileall -q providers tools server.py`, запустите сервер и прогоните smoke-тест (`/health`, `/api/providers`, транскрибацию тестового файла).
3. Создайте pull request в `main` с описанием: что меняется, зачем, как проверить.
4. CI (`.github/workflows/ci.yml`) автоматически проверит компиляцию Python и валидность JSON — дождитесь зелёного статуса.
5. Изменения API и конфигурации — с обратной совместимостью (пример: `/api/updates` по умолчанию отдаёт JSON, `?stream=1` — SSE).

## Как добавить новый провайдер

1. Создайте `providers/my_provider.py` — подкласс `Provider` (см. `providers/base.py:53`): реализуйте `is_available`, `install`, `list_models`, `is_model_downloaded`, `download_model`, `check_model_update`, `load`, `transcribe`.
2. Заполните `ProviderInfo` (название, модели, языки, hint установки).
3. Зарегистрируйте в `providers/__init__.py` (порядок = порядок в UI).
4. Готово — UI и API подхватят провайдера без изменений; не забудьте обновить списки моделей в доках.

Подробности внутреннего устройства — в [ARCHITECTURE.md](ARCHITECTURE.md).
