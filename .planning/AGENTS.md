# AGENTS.md — инструкции для AI-агентов в проекте autrau

> Этот файл — главная точка входа для AI-агентов, которые будут работать с autrau. Прочитай ПЕРЕД любыми действиями.

## Project Snapshot

- **Что это:** локальный десктопный транскрибатор аудио/видео. FastAPI + vanilla JS. GitHub: https://github.com/crosspostly/autrau
- **Стек:** Python 3.13, FastAPI, uvicorn, providers (Whisper.cpp, Faster-Whisper, Parakeet NeMo, Parakeet ONNX/DirectML)
- **UI:** один файл `index.html`, vanilla JS, без сборки, тёмная тема
- **Текущий milestone:** v1.5 — Handi-like UX (hotkey, voice memos, translation)

## Обязательно к прочтению ПЕРЕД работой

1. **`.planning/PROJECT.md`** — общее описание проекта, stack, repository layout, decisions
2. **`.planning/REQUIREMENTS.md`** — детальные требования v1.5 с REQ-IDs
3. **`.planning/ROADMAP.md`** — текущие фазы и tasks
4. **`.planning/STATE.md`** — current position, blockers, todos
5. **`.planning/MILESTONES.md`** — история версий (что уже сделано)

## Critical Conventions

### PowerShell, not bash
- Shell = **PowerShell 5.1**, не bash
- Используй `;` вместо `&&`, `Get-ChildItem` вместо `ls`, `Select-String` вместо `grep`
- **НЕ используй** `Remove-Item` — safety policy блокирует. Используй `mavis-trash` для recoverable удаления
- **НЕ используй** `&&` в PowerShell — это не bash
- Multi-statement scripts: начинай с `$ErrorActionPreference = 'Stop'`
- Wrapping regex в single quotes: `Select-String -Pattern '...'`

### Python paths
- `python` в PATH = **WindowsApps Python 3.13** stub (`C:\Program Files\WindowsApps\...`) — это сервер
- `py -3.13` = **MS Store Python 3.13** — для CLI testing
- **Устанавливай пакеты:** `py -3.13 -m pip install <pkg>` (это для сервера)
- `.venv` в репо — для разработки (lint, test, type-check)

### Encoding
- **Cyrillic в файлах** — UTF-8 (default для `open(..., encoding='utf-8')`)
- **Cyrillic в PowerShell stdout** — может сломаться (cp1252). Решения: `-X utf8` флаг, или `chcp 65001 | Out-Null` в начале
- **HTML/JS files** — UTF-8 без BOM
- **CRLF endings** для .bat файлов (cmd.exe ломается на LF)

### Server lifecycle
- Server runs on **PID порта 8000**. Проверить: `Get-NetTCPConnection -LocalPort 8000`
- Restart: `Stop-Process -Id <PID>; cd <repo>; Start-Process powershell -ArgumentList '-NoExit','-Command','.\start.bat' -WindowStyle Minimized`
- `start.bat` создаёт `.venv` если нужно, активирует его, запускает `python -m uvicorn server:app --port 8000`
- Server auto-restarts on crash через WindowsApps Python crash recovery (~60s)

### What's gitignored
- `data/` — runtime state (config.json, transcripts, voice-memos, models)
- `.venv/` — Python venv
- `tests/` — локальные test artifacts
- `_test_*.py`, `_api_check*.py`, `*.bak-*` — локальные скрипты

### Что ВСЕГДА делай перед изменениями
1. `git status -sb` — проверь clean state
2. `git log --oneline -5` — посмотри последние коммиты
3. Прочитай файлы, которые будешь менять
4. `node --check <file>` для inline JS / `ast.parse(open(<file>, encoding='utf-8').read())` для Python

### Что ВСЕГДА делай после изменений
1. Python syntax: `py -3.13 -c "import ast; ast.parse(open('<file>', encoding='utf-8').read())"`
2. JS syntax (если правил index.html inline script): extract → temp file → `node --check`
3. `git diff` — посмотри что накоммитил
4. Commit + push: `git add <files>; git commit -m "<message>"; git push`
5. Restart server если менял server.py / providers/ / tools/
6. Verify в браузере: `http://localhost:8000`

## Common Pitfalls

| Pitfall | Fix |
|---------|-----|
| `&&` в PowerShell | Используй `;` |
| `Remove-Item` blocked | `mavis-trash` или move to backup |
| `cmd /c file.bat` exit code 1 | LF endings вместо CRLF в .bat — конвертни |
| `genx` is not recognized | Variable name shadowing — переименуй |
| `UnicodeEncodeError` в PowerShell | `-X utf8` или ASCII output |
| Server not running | `Start-Process powershell -ArgumentList '-NoExit','-Command','.\start.bat' -WindowStyle Minimized` |
| 30-min background bash timeout | Используй `cron self` для long-running tasks |
| faster-whisper в дропдауне | Скрыт в UI явно (`p.name === 'faster-whisper'`) — но provider всё ещё `installed: true` |
| Transcript filename без расширения | `tools/cleanup.py::save_transcript` сохраняет `.mp3.txt` (Phase 1) |
| `0.0 МБ` для маленьких файлов | Backend отдаёт `size_kb`, UI показывает `КБ` если < 1 МБ (Phase 1) |

## Architecture Quick Reference

```
index.html            → UI (vanilla JS, inline)
server.py             → FastAPI app, all endpoints, streaming via SSE
providers/            → Transcription providers (4 files + base + __init__)
  base.py             → Abstract Provider class, ProviderInfo, Segment
  whisper_cpp.py      → pywhispercpp wrapper (CPU only)
  faster_whisper.py   → CTranslate2 wrapper (NVIDIA, hidden in UI)
  parakeet.py         → NeMo (NVIDIA, hidden in UI)
  parakeet_onnx.py    → ONNX/DirectML (any GPU/CPU)
tools/
  config.py           → load/save config + defaults
  cleanup.py          → save_transcript, list_transcripts, run_cleanup
  favorites.py        → star-marked files (protected from cleanup)
  check.py            → health check
  updates.py          → git pull + pip upgrade
data/                 → gitignored
  config.json         → user config
  transcripts/        → saved .txt files (with source ext like .mp3.txt)
  models/             → downloaded model files
  favorites.json      → starred files
```

## Workflow per Phase

См. `.planning/ROADMAP.md` для деталей. Общий подход:

1. **Читай** ROADMAP.md → выбери sub-phase
2. **Читай** REQ в REQUIREMENTS.md → пойми acceptance criteria
3. **Сделай** task(s)
4. **Тестируй** (юнит + UI inspect)
5. **Коммить** с message типа `phase N: <sub-phase name>`
6. **Push** и restart server
7. **Обнови** STATE.md (mark todo done)

## Memory Discipline

- Если узнал что-то reusable про autrau → пиши в **agent memory** (`memory(target=main)`)
- Если узнал про user preference → **user memory** (`memory(target=user)`)
- Если узнал про autrau-специфику → **project memory** (править `.planning/AGENTS.md` или topic файл)
- НЕ спамь memory мелочами (transient state, raw logs, etc.)

## Active Skills (используй когда applicable)

- `sp-00-using-superpowers` — meta, всегда
- `sp-01-brainstorming` — для новой фичи перед planning
- `sp-02-writing-plans` — для multi-step tasks
- `sp-03-subagent-driven-dev` — для parallel tasks
- `sp-04-tdd` — для фич/багов с тестами
- `sp-06-systematic-debugging` — для багов
- `sp-07-verification` — перед "готово"
- `gsd-*` — для GSD workflow

## Hot tips

- **Server logs:** `autrau-server.out.log` и `autrau-server.err.log` в корне репо
- **Config:** `data/config.json` — локальный, можно смотреть текущие настройки юзера
- **Models dir:** `data/models/<provider>/<model-name>/`
- **Transcripts dir:** `data/transcripts/*.txt` (с source ext в имени)
- **Voice memos dir:** `data/voice-memos/*.txt` (Phase 2)
- **Test data:** `tests/_*.txt` (gitignored)

---

*Maintained by: AI agents + human. Last update: 2026-08-19*
