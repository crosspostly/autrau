---
gsd_state:
  version: 5
  milestone: v1.7
  status: complete
  current_phase: 7
  current_phase_name: "Telegram agent bot"
  last_updated: 2026-08-20
previous_milestone: v1.5.8
next_milestone: v1.6
next_milestone_plan: "Tauri/Electron wrapper (portable .exe) — DEFERRED, plan in C:\\obsidian"
---

# State — v1.6.0 (Electron desktop MVP) ✅ COMPLETE

## Current Position

**Milestone:** v1.6.0 «Electron desktop wrapper MVP» ✅ DONE (2026-08-20)
**Phase:** 8 (v1.6.0 = MVP foundation)
**Repo:** https://github.com/crosspostly/autrau-desktop (commit e50c310)

**Done ранее:**
- v1.5 milestone (Handi-like UX) ✅
- v1.5.1-5 hot-fix series ✅
- v1.5.6 SRT/VTT/JSON export ✅
- v1.5.7 Vibe-inspired (CLI / yt-dlp / system-audio / Swagger / AGENTS) ✅
- v1.5.8 Real auto-update ✅
- gsd-docs-update (v1.5.7+v1.5.8 docs coverage) ✅
- **v1.7 Telegram agent bot** ✅ — 11 команд, voice/audio, agent-mode /ask
- **v1.7.1 QA-фокус** ✅ — добавлены `/diag /logs /test /update apply`, 13 FAQ-паттернов
- **v1.6.0 Electron desktop MVP** ✅ — Electron + sidecar + tray + hotkey + window

**Next action:** v1.6.1 (PyInstaller sidecar) или v1.6.2 (polish + build pipeline)

## v1.7 new files

- `tools/telegram_bot.py` (35109 bytes) — main bot, 9 FAQ patterns, 10 commands
- `tests/test_telegram_bot.py` (5130 bytes) — 19/19 unit tests passing
- `start_telegram_bot.bat` (1335 bytes) — 1-click launcher

## v1.7 modified files

- `tools/config.py` — +3 keys (telegram_bot_token, telegram_allowed_chat_ids, telegram_api_url)
- `requirements.txt` — +python-telegram-bot note (opt-in, не в base)
- `index.html` — Telegram bot info card in settings
- `README.md` — Telegram agent bot section, structure tree updated
- `docs/CONFIGURATION.md` — 3 new config keys documented
- `docs/ROADMAP.md` — Telegram-бот moved from "идея" to "✅ сделано 2026-08-20 (v1.7)"

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
| **v1.5.6**    | ✅ done       | 2026-08-19 | b18442d — SRT/VTT/JSON/TXT export                  |
| **v1.5.7**    | ✅ done       | 2026-08-20 | 7341911, d1d43dd, 8198aa3, f843bdb, c3e379d        |
| **v1.5.8**    | ✅ done       | 2026-08-20 | 9397dc5 — Real auto-update                         |
| **docs-update** | ✅ done     | 2026-08-20 | ca1da40 — gsd-docs-update cycle                    |
| **v1.7**      | ✅ done       | 2026-08-20 | TBD — Telegram agent bot                           |

## Hot fixes (вне phase)

(см. `git log --oneline` за последние дни)

## v1.7 lessons

- **Per-chat whitelist:** по умолчанию пустой список = блок всех (безопасный дефолт).
  Пользователь ОБЯЗАН явно добавить свой chat_id. Узнать: открыть `start_telegram_bot.bat`,
  попробовать `/start` — бот пришлёт `chat_id`.
- **python-telegram-bot v21.x async:** все хэндлеры `async def`, нужно `Application.builder().token().build()`.
- **SSE парсинг на клиенте:** raw HTTP через http.client + ручной split по `\n\n` —
  в urllib нет SSE. На больших файлах (>1MB аудио) chunked response может задержать
  прогресс — ок, бот просто не обновляет message пока percent не изменится.
- **ffmpeg ogg→wav:** Telegram шлёт `.ogg` (opus). onnx-asr/faster-whisper его обычно
  принимают, но для универсальности — конвертируем в wav 16kHz mono через ffmpeg.
- **FAQ-паттерны:** 9 regexp'ов — argos, parakeet, youtube, system audio, slow, error,
  update, video, provider switch. Свободный текст с `?` или вопросительным словом
  роутится в `/ask`. Fallback: предложить `/check`.
- **Telegram Bot API 20MB лимит** на скачивание voice/audio. Длинные голосовые
  (>20MB) — нужно резать или использовать local upload.
- **Test isolation:** `cfg.init(path=tmp)` в начале тестов — не трогаем реальный config.
  Используем `tempfile.TemporaryDirectory` для state-тестов, mock urllib для API.
- **20MB лимит → warn рано:** проверяем `voice.file_size` ДО скачивания, чтобы
  не качать пол-файла перед отказом.

## v1.6 (Tauri/Electron) — DEFERRED

Plan: `C:\obsidian\04_Knowledge\projects\autrau\v1.6-tauri-plan.md`
Decision: Electron > Tauri (Node.js уже установлен; Tauri требует 5GB Rust + MSVC toolchain
для 5-10MB binary savings на single-user utility — нерентабельно).
