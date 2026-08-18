# Milestones

## v1.0 — Initial Release (shipped)

- FastAPI сервер с `/transcribe` (SSE streaming)
- 4 провайдера: whisper-cpp, faster-whisper, parakeet (NVIDIA), parakeet-onnx (DirectML)
- UI: 1-page vanilla JS, тёмная тема
- Favorites (★) + auto-cleanup по дням
- Lazy model loading
- Config через `data/config.json`
- GitHub Actions CI

## v1.1 — Parakeet v3 + UI Polish (shipped)

- Новый провайдер `parakeet-onnx` (SOTA 2025-2026, 25 языков, AMD-совместимый)
- Метаданные моделей (speed/accuracy/lang badges)
- Cleanup после N дней (настраивается)
- Docs: CONFIGURATION.md, ROADMAP.md
- MAX_UPLOAD_MB лимит на загрузку (413)

## v1.2 — UI/UX Cleanup (shipped)

- Удалена кнопка "Загрузить в память" (ленивая загрузка)
- FFmpeg progress для видео
- `m4a` в поддерживаемых форматах
- SVG favicon
- `transcriptionCard` (объединил LiveCard + ResultCard)
- Прогресс-метки фаз
- "Загрузить модель" → авто при первой транскрипции
- Диагностика под `<details>`

## v1.3 — Audio/Video + Queue (shipped)

- Model presets (быстрая/сбалансированная/тщательная)
- Multi-file queue
- Бронебойный canvas-smoke-test для анимаций
- Preset labels динамически по скачанным моделям
- Не-установленные провайдеры скрыты из дропдауна
- Whisper-cpp models trimmed до tiny + large-v3

## v1.4 — Bulk Selection (shipped)

- "Выбрать все" + чекбоксы в очереди
- "Выбрать все" + чекбоксы в списке расшифровок
- Скрытие "только русские" фильтра (бесполезен)
- Скрытие faster-whisper из дропдауна (AMD бесполезен)
- Размер в КБ для маленьких файлов
- Расширение исходного файла в имени транскрипта
- Git sync: `dc9ce30` → `0791b32` → `d2dca74` → `3d10ebc` (последний)

## v1.5 — Handi-like UX (текущий)

- 🔄 Горячие клавиши для реал-тайм записи
- 🔄 Автоперевод ru→en
- 🔄 Вкладка «Голосовые заметки»
- ✅ Расширение файла + KB (вне фазы, hotfix)

---

## Roadmap (next)

- v1.6 — Portable Windows exe (PyInstaller, Handy-style "1 exe, всё внутри")
- v2.0 — Speaker diarization
- v2.0 — iOS/Android remote client (LAN)
