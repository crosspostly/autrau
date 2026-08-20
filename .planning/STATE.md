---
gsd_state:
  version: 3
  milestone: v1.5.7
  status: complete
  current_phase: 5
  current_phase_name: "Vibe-inspired quick wins"
  last_updated: 2026-08-20
previous_milestone: v1.5
next_milestone: v1.6
next_milestone_plan: "Real auto-update (v1.5.8) → Tauri wrapper (v1.6)"
---

# State — v1.5.7 (Vibe-inspired quick wins) ✅ COMPLETE

## Current Position

**Milestone:** v1.5.7 «Vibe-inspired quick wins» ✅ DONE (2026-08-20)
**Phase:** 5 — все 5 sub-phases shipped
**Source:** `C:\obsidian\04_Knowledge\wiki\open-source-vibe-analysis.md`
**Plan:** `.planning/phases/5-vibe-inspired/PLAN.md`

**Done ранее:**
- v1.5 milestone (Handi-like UX) ✅
- v1.5.1-5 hot-fix series ✅
- v1.5.6 SRT/VTT/JSON export ✅
- v1.5.7 Vibe-inspired ✅ (commits 7341911, d1d43dd, 8198aa3, f843bdb)

**Next action:** v1.5.8 — Real auto-update (доделать `auto_update_app`)

## v1.5.7 Commits (4)

```
f843bdb  v1.5.7.5: AGENTS.md update + Swagger /docs
8198aa3  v1.5.7.3: system audio loopback (Windows WASAPI)
d1d43dd  v1.5.7.2: yt-dlp endpoint + UI
7341911  v1.5.7.1: CLI tool (python -m autrau.cli)
```

## Progress

| Phase         | Status       | Done at    | Commits / scope                                    |
|---------------|--------------|------------|----------------------------------------------------|
| 1             | ✅ done       | 2026-08-19 | 3d10ebc                                            |
| 2             | ✅ done       | 2026-08-19 | 428db5c, f32af6e, 1f829f1, 6b5c47f, ca29069, 64b4934 |
| 3             | ✅ done       | 2026-08-19 | f13bdb6, 8f7428e, 358992f                          |
| 4             | ✅ done       | 2026-08-19 | docs + .planning update                            |
| **v1.5.1**    | ✅ hot-fix    | 2026-08-19 | d874d09 — Argos Translate локально (~336 МБ)       |
| **v1.5.2**    | ✅ hot-fix    | 2026-08-19 | e64ea7c — preflight + auto-install Argos на старте |
| **v1.5.3**    | ✅ hot-fix    | 2026-08-19 | 9c17ea5 — автоперевод ON + Handy-style оверлей     |
| **v1.5.4**    | ✅ hot-fix    | 2026-08-19 | d28bee1 — EN/RU табы + insert-at-cursor (Handy)    |
| **v1.5.5**    | ✅ hot-fix    | 2026-08-19 | d5ea4da — .txt открывается в браузере              |
| **v1.5.5.b**  | ✅ hot-fix    | 2026-08-19 | eed46e1 — files vs voice-memos в карточке          |
| **v1.5.5.c**  | ✅ hot-fix    | 2026-08-19 | c5c8e41 — UI: убрать misleading "import завис"      |

## Hot fixes (вне phase)

- ✅ Расширение файла в имени транскрипта (REQ-v1.5-001)
- ✅ Размер в КБ (REQ-v1.5-002)
- ✅ EN/RU табы в карточке (v1.5.4)
- ✅ Voice-memos inline disposition (v1.5.5)

## Active Blockers

Нет.

## Pending Todos

### v1.5.6 — SRT/VTT/JSON экспорт (NEXT, быстрый win)
- [ ] 6.1: `POST /api/transcripts/{name}/export?format=srt|vtt|json` — использует
       `segments` из `/transcribe` ответа (faster-whisper отдаёт таймстампы слов/сегментов)
- [ ] 6.2: кнопка «💾 Экспорт» в карточке результата (в actions) с dropdown
- [ ] 6.3: UI — при отсутствии таймстампов (file uploaded без сохранения segments)
       → graceful fallback «Скачать только .txt» с подсказкой
- [ ] 6.4: tests для format конвертеров
- [ ] 6.5: docs/API.md + docs/ROADMAP.md

### v1.6 — Portable Windows .exe (Electron + PyInstaller)
- [ ] **Этап 1: scaffold** — `autrau-desktop/` рядом с `autrau/`, `npm init + i electron`
- [ ] **Этап 2: sidecar** — `pyinstaller --onefile --name autrau-server server.py` (~30 МБ)
- [ ] **Этап 3: native window** — `frame: false`, transparent, always-on-top toggle
- [ ] **Этап 4: system tray** — icon + context menu (open/hide/always-on-top/exit)
- [ ] **Этап 5: global hotkey** — `globalShortcut.register('Alt+R', ...)`
- [ ] **Этап 6: auto-start** — `app.setLoginItemSettings({openAtLogin, openAsHidden})`
- [ ] **Этап 7: portable .exe** — `electron-builder --win portable` (~180 МБ)
- [ ] **Этап 8: polish** — иконки, splash, graceful shutdown, crash recovery

Решение: **Electron вместо Tauri** (Node v24 уже есть, не нужно 5 ГБ Rust + MSVC).

### v2.0 — Telegram-бот (по запросу)
- [ ] backend: `python-telegram-bot` или `aiogram`
- [ ] bot commands: `/start`, `/transcribe` (reply на voice/audio), `/lang`, `/export`
- [ ] лимиты: Bot API 20 МБ на файл, > 20 МБ резать на чанки
- [ ] deploy: рядом с сервером, токен в `.env`

## Recent Commits (last 9)

```
c5c8e41  fix(ui): убрать 'import завис' и 'restart сервера' в install-argos UX
eed46e1  fix: разделить translation для файлов и голосовых, убрать 3.5
d28bee1  v1.5.4: EN/RU табы в карточке результата + Handy-style вставка в курсор
d5ea4da  fix(voice-memos): клик по .txt открывает в браузере, а не скачивает
9c17ea5  v1.5.3: автоперевод ON по умолчанию + плавающее окошко записи (Handy-style)
e64ea7c  v1.5.2: видимый preflight + авто-установка Argos при старте
cc1148a  docs: финал manifest для gsd-docs-update (v1.5.1)
d89c62c  docs: синхронизировано с v1.5.1 (Argos Translate + UI в шестерёнке)
d874d09  v1.5.1: Argos Translate — локальный движок, EN<->RU, ~336 МБ
```

## Server Status

- **PID:** зависит от запуска (auto-restart через WindowsApps Python crash recovery)
- **Python:** WindowsApps Python 3.13, сервер в `.venv\Scripts\python.exe`
- **Listen:** `http://127.0.0.1:8000/`
- **Argos models:** `~/local/share/argos-translate/packages/{translate-en_ru-1_9, translate-ru_en-1_9}`

## Open Questions

1. **Tauri vs Electron vs PyWebView для v1.6** — РЕШЕНО: Tauri (бинарь меньше, WebView2
   на Windows, native global hotkey, system tray из коробки).
2. **Bundling Python sidecar** — PyInstaller vs Nuitka. PyInstaller проще, Nuitka быстрее
   на старте. Начать с PyInstaller.
3. **Single .exe с моделями или без?** — Whisper модели слишком большие для бандла.
   Решение: дефолтный бандл = exe + UI, модели скачиваются при первом запуске.
4. **Глобальный хоткей default** — `Alt+R` без конфликтов. `Ctrl+Shift+R` пусть остаётся
   in-browser fallback.

## Decisions (принято)

- [x] Translation provider default = `argos` (локально, ~336 МБ, без облака)
- [x] Translation fallback = `libretranslate` (если argos недоступен; public instances
      мёртвы, но если юзер поднял self-host — работает)
- [x] `translate_to_en = true` by default (v1.5.3)
- [x] Voice memos в `data/voice-memos/`, не в `data/transcripts/`
- [x] Hotkey default = `Ctrl+Shift+R` (можно настроить в шестерёнке)
- [x] Глобальный хоткей только в v1.6 (Tauri), v1.5 — in-browser
- [x] Files vs voice-memos: файлы показывают только оригинал в карточке, голосовые —
      обе вкладки EN/RU

## Key Context

- Server runs on `.venv\Scripts\python.exe` (venv), не на WindowsApps Python напрямую
- `data/` is gitignored — runtime файлы (config, transcripts, voice-memos, models)
- Providers в `providers/` — `whisper-cpp` (CPU), `parakeet-onnx` (CPU/DirectML)
- `faster-whisper` и `parakeet` — скрыты из UI dropdown (CPU-only, бесполезны на AMD GPU)
- UI: vanilla JS, всё в `index.html` (без сборки)
- Translation providers (real-time 2026-08-19): ✅ argos, ✅ libretranslate (код жив, public
  instances мертвы), ✗ minimax (нужен API key)
- `translate(text, source=source)` в Argos — БАГ (нет такого параметра). Используем
  `langdetect` + Cyrillic-эвристику.
- Server logs: `autrau-server.out.log` (UTF-8, append, FileHandler), `autrau-server.err.log`

---

*Last updated: 2026-08-19 23:05 UTC+3*
