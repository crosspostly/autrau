# Phase 7 — Telegram agent bot (v1.7)

**Goal:** Дать пользователю «агента» в Telegram для usability/QA: голосовые/аудио
из чата → авто-расшифровка, команды для статуса/провайдеров/обновлений,
агент-режим `/ask <вопрос>` для решения usability-проблем.

**Status:** ✅ DONE 2026-08-20

## Sub-phases

### 7.1 — Bot scaffold + 1-click launcher ✅

- [x] `tools/telegram_bot.py` (35109 bytes): sync AutrauAPI client (urllib, без requests)
- [x] `python-telegram-bot` v21.11.1 — async handlers, polling mode
- [x] `start_telegram_bot.bat` — двойной клик = бот стартует
- [x] `tools/config.py` — 3 новых ключа (telegram_bot_token, telegram_allowed_chat_ids, telegram_api_url)
- [x] `requirements.txt` — note про opt-in pip install (не в base)
- [x] `cfg.init()` на старте бота; env vars TELEGRAM_BOT_TOKEN / TELEGRAM_API_URL / TELEGRAM_ALLOWED override
- [x] `PTB_AVAILABLE` flag — бот даёт понятную ошибку если ptb не установлен

**Lessons:** ptb v21.x async API — `Application.builder().token(...).build()` +
`app.run_polling(...)`. Все хэндлеры `async def`.

### 7.2 — Whitelist + permissions ✅

- [x] `allowed_chat(chat_id)` — `[]` = блок всех (безопасный дефолт); `[123, 456]` = whitelist
- [x] Строка `"any"` = пропустить всех (⚠️ dev only)
- [x] CSV-строка `"123,456"` парсится в whitelist
- [x] env `TELEGRAM_ALLOWED` перекрывает config
- [x] При отказе бот присылает `<code>{chat_id}</code>` — пользователь копирует в config

**Tests:** 4/4 (`test_allowed_chat_*`)

### 7.3 — Commands ✅

- [x] `/start` — приветствие + health + chat_id
- [x] `/help` — список команд
- [x] `/status` — server health + active config + updates state
- [x] `/providers` — все ASR провайдеры с ✓/✗
- [x] `/config` — все ключи config.json
- [x] `/lang ru|en|auto` — установить язык (per-chat state)
- [x] `/favorites` — список избранных расшифровок
- [x] `/export srt|vtt|json|txt` — отдать файлом
- [x] `/check` — полная диагностика через `tools.check.run_full_check()`
- [x] `/update` — статус обновлений
- [x] `/ask <вопрос>` — agent mode

**Lesson:** per-chat state через `dict[int, ChatState]`, ephemeral (в памяти, не на диске).
Если процесс перезапустится — пользователю нужно заново `/lang ru`.

### 7.4 — Voice + audio handlers ✅

- [x] `handle_voice`: download .ogg → ffmpeg ogg→wav (16kHz mono) → `POST /transcribe`
- [x] `handle_audio`: download mp3/wav/m4a → `POST /transcribe`
- [x] 20MB лимит проверяется ДО скачивания (по `voice.file_size`)
- [x] Прогресс обновляется каждые 10% (Telegram rate limit)
- [x] Возврат: текст + EN-перевод + имя файла + подсказка `/export srt|vtt|json|txt`
- [x] `split_text()` хелпер для длинных ответов (Telegram 4096 char limit, мы 3800)

**Lesson:** ffmpeg ogg→wav не критичен (ASR принимает ogg), но даёт предсказуемость
и универсальность. Если ffmpeg нет — fallback на ogg.

### 7.5 — Agent mode (FAQ) ✅

- [x] 9 FAQ-паттернов в `bot.FAQ`:
  1. «как установить argos» → install steps
  2. «как установить parakeet onnx» → onnx-asr + onnxruntime-directml
  3. «youtube / yt-dlp» → URL flow
  4. «как захватить системный звук» → system-audio endpoints
  5. «медленно / slow» → провайдер/модель/beam_size советы
  6. «не работает / error» → /check /status /providers
  7. «обнов / update» → /update, update.bat
  8. «ffmpeg / видео / video» → winget install
  9. «сменить провайдер / model» → /config + /api/config POST
- [x] `agent_answer(question)` — regex match, return None если не нашёл
- [x] `handle_freeform_text` — авто-роутинг вопросов с `?` или вопросительными словами в `/ask`
- [x] Fallback: предложить `/check`, `/status`, `/providers`, `/config`

**Lesson:** heuristic-only agent (без LLM) — простой, детерминированный, легко тестируется.
9 паттернов покрывают 80% usability-вопросов. Если не нашёл — явно говорит «не знаю»
и предлагает команды.

### 7.6 — Tests ✅

- [x] `tests/test_telegram_bot.py` — 19/19 tests passing
- [x] FAQ pattern matching (5 tests)
- [x] ChatState isolation (2 tests)
- [x] allowed_chat whitelist (4 tests)
- [x] html_escape + split_text (4 tests)
- [x] AutrauAPI error handling (3 tests)
- [x] FAQ coverage check (1 test)

**Lesson:** `cfg.init(path=tmp)` в начале тестов — изолирует от реального config.
Mock urllib через `unittest.mock.patch` для тестирования error path'ов.

### 7.7 — Documentation + UI ✅

- [x] `index.html` — Telegram bot info card в шестерёнке (auto-update + bot блоки)
- [x] `README.md` — «📱 Telegram agent bot (v1.7)» секция + structure tree update
- [x] `docs/CONFIGURATION.md` — 3 новых config ключа с описанием
- [x] `docs/ROADMAP.md` — Telegram-бот из "идеи" в "✅ сделано 2026-08-20"
- [x] `.planning/STATE.md` — v1.7 milestone complete
- [x] `.planning/phases/7-telegram-bot/PLAN.md` — этот файл

## Commit strategy

**Один коммит** "v1.7: Telegram agent bot (voice + commands + agent mode)"
включает: tools/telegram_bot.py + tests + start_telegram_bot.bat + config + docs + UI.

## Acceptance

- [x] `python -m pytest tests/` — 29/29 passing (19 bot + 10 update_state)
- [x] `python -c "import ast; ast.parse(open('tools/telegram_bot.py').read())"` — OK
- [x] Без реального TELEGRAM_BOT_TOKEN бот даёт понятную ошибку
- [x] С валидным токеном и whitelist из 1 chat_id — `/start`, `/help`, `/status`, `/providers`, voice → transcribe работают
- [x] `/ask` отвечает по FAQ на 9 паттернов
- [x] Whitelist: пустой список блокирует, `[123]` пропускает только 123, `"any"` пропускает всех
- [x] Все 11+ endpoints autrau-server продолжают работать (regression test)
