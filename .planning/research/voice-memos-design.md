# Research: Voice Memos + Hotkey Design (v1.5)

> Исследование дизайна для REQ-v1.5-003 (hotkey) и REQ-v1.5-005 (голосовые заметки). Принятые решения, альтернативы, trade-offs.

## Date: 2026-08-19
## Status: Decision made (v1.5 plan locked in)

---

## Hotkey: in-browser vs global (system-wide)

### Decision
**v1.5: in-browser only** (хоткей работает только когда вкладка autrau в фокусе).

### Why
- Глобальный хоткей требует native wrapper (Electron, Tauri, Python `keyboard` lib)
- Electron/Tauri = отдельный крупный проект (планируется v1.6 portable exe)
- `keyboard` (Python) требует admin rights на Windows, fragile
- In-browser через `keydown` listener — стандарт, работает везде

### Trade-off
- Юзер должен вернуть фокус в браузер чтобы использовать хоткей
- Workaround: floating overlay + browser notification when tab is hidden
- v1.6 (Electron wrapper) решит это полностью

### Alternatives considered
| Alt | Pros | Cons | Decision |
|-----|------|------|----------|
| In-browser keydown | Simple, no deps, works everywhere | Только когда вкладка в фокусе | ✅ v1.5 |
| Global via `keyboard` (Python) | System-wide | Admin rights, fragile, Win-only | ❌ отклонено |
| Global via Electron | Full native UX | Big project, переписать UI | v1.6 |
| Global via Web API (Permissions Policy) | Browser-side, modern | Не поддерживается стабильно | ❌ отклонено |

---

## Audio capture: MediaRecorder vs Web Audio API

### Decision
**`MediaRecorder` API** для записи, отправка чанков через `fetch` на backend.

### Why
- `MediaRecorder` — стандарт W3C, поддерживается всеми браузерами
- Встроенное сжатие (Opus кодек → 32 kbps при 48kHz)
- Автоматически разбивает на chunks с `timeslice` параметром
- Можно использовать `audio/webm;codecs=opus` (хорошее качество, малый размер)

### Trade-off
- `MediaRecorder` не даёт доступа к raw PCM, нужно ждать `dataavailable` event
- Для совместимости с backend (который принимает файлы) — opus/webm работает
  - Backend умеет ffmpeg → wav если нужно

### Alternatives considered
| Alt | Pros | Cons | Decision |
|-----|------|------|----------|
| MediaRecorder | Standard, simple, opus compression | Не raw PCM | ✅ v1.5 |
| Web Audio API + AudioWorklet | Raw PCM, низкий latency | Сложнее, больше кода | ❌ overkill для v1.5 |
| `navigator.mediaDevices.getUserMedia` + manual PCM | Полный контроль | Way too complex | ❌ отклонено |

---

## Transport: HTTP chunks vs WebSocket

### Decision
**HTTP POST chunks каждые 500ms** через `fetch`.

### Why
- Простая реализация на backend (FastAPI уже принимает multipart files)
- Server-side можно не держать WebSocket-соединение (легче в обслуживании)
- Для финальной транскрипции всё равно нужен HTTP POST
- Live partials (если потоковые) — позже через polling `/api/voice/live/{id}` каждые 500ms

### Trade-off
- HTTP overhead на каждый chunk (~200 bytes header + 6KB opus audio)
- При 500ms интервале = ~12KB/sec на overhead, не критично
- Нет duplex (server не может пушить live partials без polling)

### Alternatives considered
| Alt | Pros | Cons | Decision |
|-----|------|------|----------|
| HTTP POST chunks | Simple, works everywhere | Overhead per chunk | ✅ v1.5 |
| WebSocket | Duplex, low overhead | Сложнее, server state | ❌ для v1.5 (можно v2) |
| Server-Sent Events (SSE) | One-way push, simple | Только server→client | ❌ для аудио в эту сторону |

---

## Streaming live transcription: yes or no

### Decision
**v1.5: NO streaming live transcription.** Только финальный результат по `stop`.

### Why
- Streaming требует VAD (voice activity detection) для определения пауз
- Каждый chunk нужно транскрибировать отдельно → N× время
- Объединение partial results — non-trivial
- Без VAD — partial на 3-секундном чанке не имеет смысла

### v1.5 UX
- Юзер говорит
- На overlay: красная pulse-точка + таймер
- На stop: spinner "транскрибирую..." → финальный текст
- Финальный текст сохраняется в `data/voice-memos/`

### v1.5.1 / v2 idea
- WebSocket + VAD (Silero VAD, ONNX) → partial каждые 3 сек
- На overlay появляется текст по мере речи
- Финальный текст приходит через 1-2 сек после stop

---

## Storage: data/voice-memos/ vs data/transcripts/

### Decision
**Отдельная папка** `data/voice-memos/`.

### Why
- Голосовые заметки имеют другую семантику (короткие, частые, разные потребности)
- Отдельный `voice_memo_cleanup_after_days` (default 7 дней, vs `cleanup_after_days` для файлов)
- Не смешивается с большими транскриптами видео/подкастов
- Можно мигрировать / удалять независимо

### Folder structure
```
data/
├── transcripts/         # большие расшифровки видео/аудио
│   ├── 2026-08-19_voice-123.mp3.txt
│   ├── 2026-08-19_recording.webm.txt
│   └── ...
├── voice-memos/         # короткие записи с хоткея
│   ├── 2026-08-19_18-45-12.txt
│   ├── 2026-08-19_19-02-31.txt
│   └── ...
├── models/
├── favorites.json       # ⭐ для transcripts (имя файла + категория)
└── config.json
```

### Note
favorites.json может иметь вид:
```json
{
  "transcripts:2026-08-19_voice-123.mp3.txt": true,
  "voice-memos:2026-08-19_18-45-12.txt": true
}
```

Или два файла: `favorites.json` + `favorites_voice.json`. **Decision: один общий с префиксом категории.**

---

## Config schema additions

```jsonc
// data/config.json (новые поля)
{
  // ... existing fields ...

  // Hotkey
  "hotkey": "Ctrl+Shift+R",        // default; "" = disabled

  // Voice memos
  "voice_memo_dir": "data/voice-memos/",
  "voice_memo_cleanup_after_days": 7,

  // Translation (Phase 3)
  "translate_to_en": false,
  "translation_provider": "libretranslate",  // or "minimax" or "local-nllb"
  "libretranslate_url": "",                    // empty = try public, else local
  "minimax_api_key": ""                        // from auth.json
}
```

Defaults в `tools/config.py`:
```python
DEFAULTS = {
    # ... existing ...
    "hotkey": "Ctrl+Shift+R",
    "voice_memo_dir": "data/voice-memos/",
    "voice_memo_cleanup_after_days": 7,
    "translate_to_en": False,
    "translation_provider": "libretranslate",
    "libretranslate_url": "",
    "minimax_api_key": "",
}
```

---

## Default hotkey: Ctrl+Shift+R vs Alt+R

### Decision
**Default: `Ctrl+Shift+R`**, но юзер может поменять в UI.

### Why Ctrl+Shift+R
- Похоже на Handi.app (они используют Ctrl+Shift+Space, но для демонстрации)
- R = Record — интуитивно
- Shift modifier уменьшает вероятность случайного срабатывания

### Conflict warning
- `Ctrl+Shift+R` = hard reload в Chrome. Когда фокус на autrau — не критично, но если юзер случайно нажмёт — браузер перезагрузит страницу.
- Workaround: capture and `preventDefault()` для зарегистрированного хоткея

### Alt+R
- Менее конфликтный, но менее очевидный
- Alt часто используется для menu (Windows: Alt+D для адресной строки)

### Финальный выбор
**Ctrl+Shift+R + preventDefault()** + настраиваемо в UI.

---

## UI: hotkey config widget

### Design
```
┌────────────────────────────────────────────┐
│ Хоткей для записи:                         │
│ ┌──────────────────┐                       │
│ │ Ctrl+Shift+R     │  [Записать] [Сброс]  │
│ └──────────────────┘                       │
│ Нажмите сочетание, чтобы переназначить     │
└────────────────────────────────────────────┘
```

- Input показывает текущий хоткей
- При focus → слушает keydown → обновляет input
- «Записать» / «Сброс» (вернуть default)
- Сохранение в `cfg.hotkey` через существующий `/api/config` POST

---

## Floating overlay design

### When recording
```
┌────────────────────────────────────────────────┐
│ 🔴 Recording · 00:23 · press hotkey to stop   │
│                                                │
│ (text appears here as it's transcribed)        │
│                                                │
└────────────────────────────────────────────────┘
```

- Position: fixed, bottom-right
- Pulse animation on 🔴
- Live timer
- Esc to stop (alternative to hotkey)
- Click outside → does NOT dismiss (to avoid accidental stop)

### When stopped, transcribing
```
┌────────────────────────────────────────────────┐
│ ⏳ Транскрибирую 23 сек записи...             │
│                                                │
│ ▓▓▓▓▓▓░░░░░░░░░░  35%                        │
└────────────────────────────────────────────────┘
```

- Indeterminate progress (мы не знаем ETA)
- Disappears when result is ready

### When done
```
┌────────────────────────────────────────────────┐
│ ✅ Готово:                                     │
│                                                │
│ "Привет, это тестовая запись голосом.         │
│  Сегодня хорошая погода..."                   │
│                                                │
│ [Копировать] [Открыть] [✕]                   │
└────────────────────────────────────────────────┘
```

- Auto-dismiss after 30s or on click
- "Open" → open the .txt in `data/voice-memos/`
- "Copy" → copy text to clipboard

---

## Risks & Open Questions

1. **Microphone permission UX** — если юзер откажет, как объяснить что делать? Tooltip: "Нажмите 🔒 в адресной строке → Микрофон → Разрешить"
2. **Multiple recordings in parallel** — `MediaRecorder` per tab. Если юзер 2 раза нажмёт хоткей — ошибка или graceful merge? Decision: ошибка с понятным сообщением.
3. **Long recordings (>10 min)** — auto-stop? Decision: warning at 10 min, hard stop at 30 min, file gets saved.
4. **Tab close during recording** — `beforeunload` → `navigator.sendBeacon('/api/voice/stop')`. But if user closes browser abruptly — audio lost. Acceptable trade-off.
5. **Hotkey in input fields** — if user is typing in a text field, should hotkey work? Decision: yes, always, except in this hotkey config input itself.
6. **Browser compat** — MediaRecorder поддерживается в Chrome, Firefox, Safari (с версии 14.1). Edge — да. Автоопределение: если `navigator.mediaDevices.getUserMedia` нет — показать "обновите браузер".

---

## Future enhancements (v1.5.1 / v2)

- **WebSocket streaming** → real-time partials
- **VAD** (Silero ONNX) → пропуск тишины, faster partials
- **Auto-summarize** через LLM (MiniMax) — "сделай краткое summary"
- **Tags / projects** для группировки voice memos
- **Search across voice memos** — полнотекстовый
- **Export to Obsidian / Notion** — через `/api/export`

---

*Author: AI-агент mavis. Reviewed by: human. Date: 2026-08-19.*
