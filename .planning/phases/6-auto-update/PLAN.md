---
phase: 6
name: real-auto-update
version: v1.5.8
status: in_progress
started: 2026-08-20
estimated: 3-4 hours
---

# Phase 6 PLAN — Real auto-update (v1.5.8)

**Контекст:** `auto_update_app` в конфиге — только флаг, без реализации. Background проверка
обновлений, persistent state, UI banner, опциональный auto-apply.

**Принцип:** v1.5.7 уже имеет `/api/updates` (check) и `/api/updates/app` (run). Нужно
добавить:
- Persistent state (data/update_state.json)
- Background scheduler (periodic check)
- State endpoints
- UI banner
- Apply+restart flow

## Sub-phases

### 6.1 — `tools/update_state.py` — persistent state (30 min) [REQ-v1.5.8-001]

State в `data/update_state.json`:
```json
{
  "last_check": "2026-08-20T10:30:00",
  "current_version": "f843bdb",
  "latest_version": "abc1234",
  "available": true,
  "dismissed_version": null,
  "last_apply_at": "2026-08-19T18:00:00",
  "last_apply_result": "ok",
  "last_apply_version": "ef13358"
}
```

API:
- `load_state() -> dict` — read from disk (default if missing)
- `save_state(d: dict) -> None` — atomic write (tmp + rename)
- `mark_checked(current, latest)` — update after each check
- `mark_applied(version, result)` — update after apply
- `mark_dismissed(version)` — set dismissed_version
- `should_notify() -> bool` — return True if available AND (dismissed_version != latest)

### 6.2 — `tools/update.py` extensions (30 min) [REQ-v1.5.8-002]

- `current_version() -> str` — `git rev-parse --short HEAD` (или "unknown" если не git)
- `apply_update_only() -> dict` — git pull + pip upgrade, БЕЗ рестарта
- `mark_dismissed_for(version)` — wrapper для state

### 6.3 — Server: background scheduler + restart (45 min) [REQ-v1.5.8-003]

- На startup: 1 раз проверка (через 1s delay чтобы не блокировать)
- Каждые `check_interval_hours` (default 6): background check
- Если `auto_update_app=true` И `available`: apply + restart через `os.execv`
- Restart: re-exec `sys.executable server.py` (или `start.bat` если из под него)
- Endpoint `GET /api/updates/state` — return full state
- Endpoint `POST /api/updates/dismiss` — mark dismissed
- Modify `POST /api/updates/apply` → сохраняет state, restarts

### 6.4 — UI: update banner (30 min) [REQ-v1.5.8-004]

- Component: `#updateBanner` (initially hidden)
- Polls `GET /api/updates/state` every 30s + on init
- Shows: "🎉 v1.5.8 available (current: v1.5.7) — [Apply] [Later]"
- Apply: POST /api/updates/apply, потом polling /api/updates/state — если available=false
  → reload page (новый код загружен), иначе показать "Restarting..." спиннер
- Later: POST /api/updates/dismiss → hide banner

### 6.5 — Config + settings UI (15 min) [REQ-v1.5.8-005]

- `data/config.json`:
  - `auto_update_app: false` (default — opt-in)
  - `update_check_interval_hours: 6` (default)
- Settings gear: add toggle "🔄 Auto-update app" + interval input

### 6.6 — Tests (60 min) [REQ-v1.5.8-006]

Unit tests (`tests/test_update_state.py`, gitignored):
- `test_load_state_missing_file` → default state
- `test_save_load_roundtrip` → write + read
- `test_should_notify` → available but not dismissed → True
- `test_should_notify_after_dismiss` → dismissed same version → False
- `test_should_notify_new_version` → dismissed old, new available → True
- `test_mark_checked` → state updated
- `test_atomic_write` → file is always valid JSON

Unit tests (`tests/test_update.py`, gitignored):
- `test_current_version_from_git` → use tmp git repo
- `test_apply_update_only_dry_run` → mocked git pull, assert command called

Integration tests (manual):
- Start server with `auto_update_app=false`, check state endpoint
- Simulate "new version available" by manually editing state file
- Verify banner shows in UI
- Click Later → banner disappears
- Click Apply → server restarts (or process exits)

### 6.7 — Docs (15 min)

- `docs/CONFIGURATION.md` — add `auto_update_app` + `update_check_interval_hours`
- `docs/API.md` — add new endpoints
- `.planning/AGENTS.md` — add pitfall about update flow
- Obsidian note `C:\obsidian\04_Knowledge\projects\autrau\v1.5.8-auto-update.md`

## Risks

1. **Restart во время SSE стрима** — клиент получит обрыв connection. Acceptable.
2. **Concurrent apply** — если два клиента нажмут Apply одновременно, `app_lock` защитит.
3. **Git conflict** — если есть unstaged changes, git pull --ff-only упадёт. UI должен показать
   понятную ошибку.
4. **Windows: os.execv не работает** — нужна другая стратегия restart для Windows. Вариант:
   spawn новый процесс + exit. Или просто exit и пусть Windows crash recovery поднимет.
5. **Background thread при exit** — нужно корректно остановить scheduler thread при shutdown.

## Done criteria

- [ ] `data/update_state.json` создаётся и обновляется корректно
- [ ] Background check работает (verify в логах каждые N часов)
- [ ] `GET /api/updates/state` возвращает актуальное состояние
- [ ] `POST /api/updates/apply` обновляет state и (опционально) restart
- [ ] `POST /api/updates/dismiss` скрывает banner
- [ ] UI banner показывается когда available, скрывается после dismiss
- [ ] Auto-apply mode работает (server restart)
- [ ] Unit tests проходят
- [ ] Docs обновлены
- [ ] Все коммиты запушены
