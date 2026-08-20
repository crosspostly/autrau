<!-- generated-by: gsd-doc-writer -->
# Тестирование Autrau

## Текущее состояние

В проекте появился **точечный pytest-каркас** в `tests/` (gitignored, добавлен в v1.5.8). Качество по-прежнему обеспечивается компиляционной проверкой в CI, smoke-тестами через HTTP API и ручными сценариями — pytest дополняет это для stateful-логики, где smoke-тесты громоздки (например, persistent state в `tools/update_state.py`).

`tests/test_update_state.py` — **10/10 pass** (на v1.5.8): покрывает atomic write, thread-safety, state machine (`should_notify`, `mark_checked` сбрасывает dismissed при новой версии, `mark_applied` failures оставляют `available=True`).

## Что проверяет CI

Файл `.github/workflows/ci.yml`, запускается на `push` и `pull_request` в `main`:

| Шаг | Команда |
|---|---|
| Python 3.11, checkout | `actions/checkout@v4` + `actions/setup-python@v5` |
| Компиляция всех Python-файлов | `python -m compileall -q providers tools server.py autrau` |
| Валидность JSON | `python -c "import json; json.load(open('...'))"` для всех `*.json`, кроме `data/*` |
| Прогон unit-тестов (опционально) | `python -m pytest tests/ -v` (если `tests/` не пустая) |

## Как проверить изменения локально

### Быстрая проверка (как CI)

```bash
python -m compileall -q providers tools server.py autrau
```

### Unit-тесты (pytest)

```bash
# С pytest (если установлен: pip install pytest)
python -m pytest tests/ -v

# Или запуск напрямую (без pytest — каждый test_* вызывается вручную)
python tests/test_update_state.py
```

Ожидаемый вывод:
```
  ✓ test_load_state_missing_file_uses_defaults
  ✓ test_save_load_roundtrip
  ✓ test_atomic_write_no_partial_file
  ✓ test_should_notify_logic
  ✓ test_mark_checked_resets_dismiss_on_new_version
  ✓ test_mark_checked_clears_available_when_up_to_date
  ✓ test_mark_applied_clears_available
  ✓ test_mark_applied_failure_keeps_available
  ✓ test_concurrent_init_thread_safe
  ✓ test_corrupted_file_falls_back_to_defaults

10 passed, 0 failed
```

### Диагностика окружения

```bash
python -m tools.check
```

### Smoke-тест сервера

1. Запустите сервер: `python server.py`
2. Проверьте эндпоинты:

```bash
curl http://127.0.0.1:8000/health                      # {"status":"ok",...}
curl http://127.0.0.1:8000/api/providers               # 3 провайдера, 22 модели
curl http://127.0.0.1:8000/api/config                  # текущий конфиг
curl -N "http://127.0.0.1:8000/api/updates?stream=1"   # SSE-прогресс по моделям
```

3. Транскрибация тестового файла:

```bash
curl -N -F "file=@sample.mp3" -F "language=ru" http://127.0.0.1:8000/transcribe
```

4. Ошибочные пути:

```bash
curl -X POST http://127.0.0.1:8000/api/provider/load -H "Content-Type: application/json" -d '{"provider":"nope"}'
# → 404 со списком доступных провайдеров

curl -X POST http://127.0.0.1:8000/transcribe -F "file=@a.mp3" -F "provider=parakeet"
# → 412, если nemo_toolkit не установлен
```

5. Авто-очистка (см. [CONFIGURATION.md](CONFIGURATION.md)): после транскрибации проверьте `data/transcripts/`, затем `curl -X POST http://127.0.0.1:8000/api/cleanup -H "Content-Type: application/json" -d '{"days":0}'` — при `days=0` ничего не удаляется.

6. Translation (v1.5+):

```bash
# Статус провайдеров
curl http://127.0.0.1:8000/api/translate/providers
# → {"providers": [{"name": "argos", "available": true, "reason": "en_ru+ru_en модели установлены"}, ...]}

# Тест перевода (Argos)
curl -X POST http://127.0.0.1:8000/api/translate \
  -H "Content-Type: application/json" \
  -d '{"text": "Привет, как дела?", "target": "en", "provider": "argos"}'
# → {"translated": "Hey, how are you?", "provider": "argos", "target": "en"}

# Полный пайплайн: включить + транскрибировать + проверить .en.txt
curl -X POST http://127.0.0.1:8000/api/config \
  -H "Content-Type: application/json" \
  -d '{"translate_to_en": true, "translation_provider": "argos"}'
curl -N -F "file=@sample.mp3" -F "language=ru" http://127.0.0.1:8000/transcribe
ls data/transcripts/*.en.txt   # должен появиться файл
curl http://127.0.0.1:8000/api/transcripts  # has_translation=true, translation_name=*.en.txt
```

7. Избранное (защита от авто-очистки):

```bash
# список расшифровок (должен появиться файл после шага 3)
curl http://127.0.0.1:8000/api/transcripts

# пометить избранным (toggle)
curl -X POST http://127.0.0.1:8000/api/favorites -H "Content-Type: application/json" -d '{"name":"2026-08-17_10-00-00_sample.txt"}'
# → {"name":"...","is_favorite":true}

# явно снять ярлык
curl -X POST http://127.0.0.1:8000/api/favorites -H "Content-Type: application/json" -d '{"name":"...","favorite":false}'

# несуществующий файл → 404
curl -X POST http://127.0.0.1:8000/api/favorites -H "Content-Type: application/json" -d '{"name":"nope.txt"}'
```

Проверка защиты: при `cleanup_after_days=0` временно установите `days=1` через
`/api/cleanup`, файл старше суток при этом **не удаляется**, если он в избранном
(в ответе cleanup `protected ≥ 1`), и удаляется после снятия ярлыка.

8. Экспорт субтитров (v1.5.6+):

```bash
# После шага 3 в data/transcripts/ появится <name>.txt + <name>.segments.json
# SRT (SubRip):
curl -OJ "http://127.0.0.1:8000/api/transcripts/<name>.txt/export?format=srt"
# VTT (W3C):
curl "http://127.0.0.1:8000/api/transcripts/<name>.txt/export?format=vtt"
# JSON (с метаданными):
curl "http://127.0.0.1:8000/api/transcripts/<name>.txt/export?format=json"
```

9. URL → транскрипция (v1.5.7+):

```bash
# Метаданные (без скачивания)
curl "http://127.0.0.1:8000/api/yt-dlp/info?url=https://www.youtube.com/watch?v=dQw4w9WgXcQ"

# Транскрибировать видео (SSE)
curl -N -X POST http://127.0.0.1:8000/api/yt-dlp \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "language": "en"}'
```

10. CLI (v1.5.7+):

```bash
# В соседнем терминале (сервер должен быть запущен)
python -m autrau.cli health
python -m autrau.cli providers
python -m autrau.cli models --provider whisper-cpp
python -m autrau.cli transcribe sample.mp3 --output out.txt
python -m autrau.cli batch ./audio/ --pattern "*.{mp3,wav}" --output ./out/
```

11. Self-update (v1.5.8+):

```bash
# Текущий state (persistent в data/update_state.json)
curl http://127.0.0.1:8000/api/updates/state
# Force check
curl -X POST http://127.0.0.1:8000/api/updates/check-now
# Dismiss (если есть обновление)
curl -X POST http://127.0.0.1:8000/api/updates/dismiss
# Apply (git pull + pip upgrade; если auto_update_app=true — restart)
curl -X POST http://127.0.0.1:8000/api/updates/apply
```

## Как писать новые тесты

### Unit-тесты (pytest)

Паттерн из `tests/test_update_state.py`:
- `tests/test_<module>.py` — один файл на модуль
- Каждый тест — функция `def test_<scenario>(...):` (без классов, без фикстур)
- `tempfile.TemporaryDirectory()` для изоляции от реальных файлов
- Запуск через `python -m pytest tests/ -v` ИЛИ напрямую `python tests/test_xxx.py` (без pytest — каждый test_* вызывается вручную через `if __name__ == "__main__":`)

Пример:
```python
import tempfile
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tools import my_module as mm  # noqa: E402

def test_my_scenario():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "test.json"
        mm.init(path=path)
        mm.do_something()
        assert mm.get() == {"expected": "value"}

if __name__ == "__main__":
    import traceback
    tests = [v for k, v in globals().items() if k.startswith("test_")]
    passed = failed = 0
    for t in tests:
        try:
            t()
            passed += 1
            print(f"  ✓ {t.__name__}")
        except Exception as e:
            failed += 1
            print(f"  ✗ {t.__name__}: {e}")
            traceback.print_exc()
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)
```

### Smoke / integration

Принимаемые паттерны (использовались до pytest):
- **Одноразовые проверки** — скрипты в корне репозитория с префиксом `_` (например, `_smoketest.py`), которые добавляются в `.gitignore`.
- **Модульные проверки логики** (например, `tools/cleanup.run_cleanup`) — можно написать как автономный скрипт: создать тестовые файлы, вызвать функцию, проверить результат, удалить тестовые файлы штатным API модуля.
- **E2E через curl** — запуск сервера + curl-сценарии из этого файла (раздел «Smoke-тест сервера»).

## Покрытие

Порог покрытия не настроен (нет конфигурации coverage). Для изменений, затрагивающих логику, обязательно прогоняйте хотя бы smoke-тест соответствующих эндпоинтов или добавляйте unit-тест в `tests/`.
