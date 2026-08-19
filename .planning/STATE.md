---
gsd_state:
  version: 1
  milestone: v1.5
  status: complete
  current_phase: 4
  current_phase_name: "Polish + docs"
  last_updated: 2026-08-19
---

# State — v1.5 (Handi-like UX)

## Current Position

**Phase:** 4 — Polish + docs ✅ DONE
**Status:** milestone complete
**Next action:** start v1.6 (portable Windows exe) when ready

## Progress

| Phase | Status         | Done at    | Commits |
|-------|----------------|------------|---------|
| 1     | ✅ done         | 2026-08-19 | 3d10ebc |
| 2     | ✅ done         | 2026-08-19 | 428db5c, f32af6e, 1f829f1, 6b5c47f, ca29069, 64b4934 |
| 3     | ✅ done         | 2026-08-19 | f13bdb6, 8f7428e, 358992f |
| 4     | ✅ done         | 2026-08-19 | docs + .planning update |

## Hot fixes (вне phase)

- ✅ Расширение файла в имени транскрипта (REQ-v1.5-001)
- ✅ Размер в КБ (REQ-v1.5-002)

## Active Blockers

Нет.

## Pending Todos

### Phase 2 (hotkey + voice memos)
- [ ] 2.1: Backend voice-memos API
- [ ] 2.2: Frontend MediaRecorder + hotkey
- [ ] 2.3: UI табы в расшифровках
- [ ] 2.4: Config hotkey + voice-memo dir
- [ ] Tests для всех 2.x
- [ ] Commit per sub-phase

### Phase 3 (translation)
- [ ] 3.1: Translation provider abstraction
- [ ] 3.2: Server translate endpoint + hook
- [ ] 3.3: UI галочка + badge
- [ ] Tests

### Phase 4 (polish)
- [ ] docs/ROADMAP.md update
- [ ] docs/CONFIGURATION.md add new fields
- [ ] README.md секция про voice memos
- [ ] CI green
- [ ] Memory note

## Recent Commits (last 5)

```
3d10ebc  transcript filename: preserve source extension + show KB if < 1MB
d2dca74  add select-all checkbox to transcripts list
2f3cc90  hide faster-whisper from model dropdown (CPU-only, бесполезен на AMD GPU)
c6a5a10  remove onlyRu filter — русский фильтр больше не нужен
0791b32  queue bulk selection: select-all + checkboxes + bulk delete
```

## Server Status

- **PID:** 17712 (running on port 8000)
- **Python:** WindowsApps Python 3.13
- **Last restart:** 2026-08-19 (after Phase 1 commit)

## Open Questions

1. **Translation provider** — LibreTranslate (медленный, бесплатный), MiniMax (платный, быстрый), или NLLB-200 локальный (600MB)? Спросить юзера перед Phase 3.
2. **Hotkey default** — `Ctrl+Shift+R` (конфликтует с browser reload в некоторых браузерах) или `Alt+R` (без конфликтов)? Предлагаю `Alt+R` или сделать настраиваемым.
3. **Глобальный хоткей** — оставить только in-browser, или делать Electron wrapper? Пока in-browser.

## Decisions Pending Approval

- [ ] Hotkey default = `Ctrl+Shift+R` (можно настроить)
- [ ] Voice memos в отдельной папке `data/voice-memos/`, не в `data/transcripts/`
- [ ] Translation provider по умолчанию — LibreTranslate (если доступен) → MiniMax fallback

## Key Context

- Server runs on WindowsApps Python 3.13, не на MS Store Python
- `data/` is gitignored — все runtime-файлы (config, transcripts, voice-memos, models)
- Providers в `providers/` — `whisper-cpp`, `faster-whisper` (скрыт в UI), `parakeet` (скрыт), `parakeet-onnx`
- UI: vanilla JS, всё в `index.html` (без сборки)
- Tests в `.gitignore` — локальные `_test_*.py`, `_api_check*.py`

---

*Last updated: 2026-08-19*
