<!-- generated-by: gsd-doc-writer -->
# Тестирование Autrau

## Текущее состояние

В репозитории **нет тестового фреймворка** (pytest/jest и пр.) и нет каталога `tests/` (он добавлен в `.gitignore`). Качество поддерживается компиляционной проверкой в CI и ручными smoke-тестами. Это осознанный выбор для локального инструмента без сборки.

## Что проверяет CI

Файл `.github/workflows/ci.yml`, запускается на `push` и `pull_request` в `main`:

| Шаг | Команда |
|---|---|
| Python 3.11, checkout | `actions/checkout@v4` + `actions/setup-python@v5` |
| Компиляция всех Python-файлов | `python -m compileall -q providers tools server.py` |
| Валидность JSON | `python -c "import json; json.load(open('...'))"` для всех `*.json`, кроме `data/*` |

## Как проверить изменения локально

### Быстрая проверка (как CI)

```bash
python -m compileall -q providers tools server.py
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

6. Избранное (защита от авто-очистки):

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

## Как писать новые тесты

Официального фреймворка нет, поэтому принятые паттерны:

- **Одноразовые проверки** — скрипты в корне репозитория с префиксом `_` (например, `_smoketest.py`), которые добавляются в `.gitignore`.
- **Модульные проверки логики** (например, `tools/cleanup.run_cleanup`) — можно написать как автономный скрипт: создать тестовые файлы, вызвать функцию, проверить результат, удалить тестовые файлы штатным API модуля.
- Если появятся постоянные тесты — используйте стандартный pytest с файлами `test_*.py` и добавьте шаг `pytest` в CI (сейчас его нет).

## Покрытие

Порог покрытия не настроен (нет конфигурации coverage). Для изменений, затрагивающих логику, обязательно прогоняйте хотя бы smoke-тест соответствующих эндпоинтов.
