"""Telegram agent bot for Autrau (v1.7).

Запуск:
    .\\.venv\\Scripts\\python.exe -m tools.telegram_bot

Что умеет:
- Голосовые сообщения и аудиофайлы → авто-транскрипция через autrau API
- Команды: /start, /help, /status, /providers, /lang, /favorites, /export, /check, /update, /ask
- "Агент" режим: freeform-вопросы → диагностика, объяснения, тесты (через tools.check + config)

Конфиг в data/config.json:
    telegram_bot_token:        токен от @BotFather
    telegram_allowed_chat_ids: [123456789] — пустой список = бот отвечает только этому списку
                                            для разработки можно "any" (НЕБЕЗОПАСНО!)
    telegram_api_url:          default http://127.0.0.1:8000

Env override:
    TELEGRAM_BOT_TOKEN, TELEGRAM_API_URL, TELEGRAM_ALLOWED
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ---- bootstrap path so absolute imports work when run as `python -m tools.telegram_bot`
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ptb is heavy — import only what's needed at top
try:
    from telegram import Update
    from telegram.constants import ParseMode
    from telegram.ext import (
        Application,
        CommandHandler,
        ContextTypes,
        MessageHandler,
        filters,
    )
    PTB_AVAILABLE = True
except ImportError:
    PTB_AVAILABLE = False
    Update = None  # type: ignore
    ParseMode = None  # type: ignore
    Application = None  # type: ignore

import tools.config as cfg
import tools.check as check
import tools.update as upd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("autrau.telegram")

# ---- state (per-chat, ephemeral) ----

@dataclass
class ChatState:
    language: str = "ru"
    last_file: str = ""              # имя последнего файла для /export
    last_segments_file: str = ""     # sidecar path
    last_text: str = ""
    last_translation: str = ""
    consecutive_failures: int = 0


_STATES: dict[int, ChatState] = {}
_API_URL = "http://127.0.0.1:8000"
_MAX_AUDIO_MB = 20  # Telegram Bot API limit is 20MB per file download


# ---- API client (sync) ----

class AutrauAPI:
    """Lightweight sync client for autrau HTTP API."""

    def __init__(self, base_url: str):
        self.base = base_url.rstrip("/")

    def _request(self, path: str, method: str = "GET", *, json_body: dict | None = None,
                 timeout: float = 10.0) -> tuple[int, Any]:
        url = self.base + path
        data = None
        headers = {}
        if json_body is not None:
            data = json.dumps(json_body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                body = r.read()
                try:
                    return r.status, json.loads(body)
                except json.JSONDecodeError:
                    return r.status, body.decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8", errors="replace")
        except (urllib.error.URLError, OSError) as e:
            return 0, str(e)

    def health(self) -> dict | None:
        code, body = self._request("/health")
        return body if code == 200 else None

    def providers(self) -> list | None:
        code, body = self._request("/api/providers")
        return body.get("providers") if code == 200 and isinstance(body, dict) else None

    def config(self) -> dict | None:
        code, body = self._request("/api/config")
        return body if code == 200 and isinstance(body, dict) else None

    def transcripts(self) -> list | None:
        code, body = self._request("/api/transcripts")
        return body.get("transcripts") if code == 200 and isinstance(body, dict) else None

    def voice_memos(self) -> list | None:
        code, body = self._request("/api/voice-memos")
        return body.get("voice_memos") if code == 200 and isinstance(body, dict) else None

    def export(self, name: str, fmt: str) -> tuple[int, bytes | str]:
        url = f"{self.base}/api/transcripts/{urllib.parse.quote(name)}/export?format={fmt}"
        try:
            with urllib.request.urlopen(url, timeout=15) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8", errors="replace")
        except (urllib.error.URLError, OSError) as e:
            return 0, str(e)

    def transcribe(self, file_path: Path, language: str = "ru",
                   on_progress: Any = None) -> dict | None:
        """Multipart upload + SSE parse (sync, with manual chunked read)."""
        import http.client
        from urllib.parse import urlparse

        parsed = urlparse(self.base)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        boundary = "----autrau" + os.urandom(8).hex()

        # Build multipart body
        file_bytes = file_path.read_bytes()
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="language"\r\n\r\n'
            f"{language}\r\n"
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{file_path.name}"\r\n'
            f"Content-Type: application/octet-stream\r\n\r\n"
        ).encode("utf-8")
        body += file_bytes
        body += f"\r\n--{boundary}--\r\n".encode("utf-8")

        conn = http.client.HTTPConnection(host, port, timeout=600)
        try:
            conn.request(
                "POST", "/transcribe", body=body,
                headers={
                    "Content-Type": f"multipart/form-data; boundary={boundary}",
                    "Content-Length": str(len(body)),
                },
            )
            resp = conn.getresponse()
            if resp.status != 200:
                return {"error": f"HTTP {resp.status}: {resp.read().decode('utf-8', errors='replace')[:200]}"}
            # Parse SSE chunked
            buf = b""
            final: dict | None = None
            while True:
                chunk = resp.read(4096)
                if not chunk:
                    break
                buf += chunk
                while b"\n\n" in buf:
                    raw, buf = buf.split(b"\n\n", 1)
                    line = raw.decode("utf-8", errors="replace").strip()
                    if not line.startswith("data: "):
                        continue
                    payload = line[6:]
                    try:
                        ev = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    kind = ev.get("type")
                    if kind == "progress" and on_progress:
                        on_progress(ev.get("percent", 0), ev.get("payload", {}))
                    elif kind == "done":
                        final = ev.get("payload", {})
                    elif kind == "error":
                        return {"error": ev.get("payload", {}).get("message", "unknown")}
            return final
        finally:
            conn.close()


# ---- helpers ----

def get_state(chat_id: int) -> ChatState:
    if chat_id not in _STATES:
        _STATES[chat_id] = ChatState()
    return _STATES[chat_id]


def api() -> AutrauAPI:
    base = os.environ.get("TELEGRAM_API_URL") or cfg.get("telegram_api_url") or _API_URL
    return AutrauAPI(base)


def allowed_chat(chat_id: int) -> bool:
    """Return True if chat_id may interact with the bot."""
    raw = os.environ.get("TELEGRAM_ALLOWED") or cfg.get("telegram_allowed_chat_ids", [])
    if isinstance(raw, str):
        if raw.strip().lower() in ("", "none", "[]"):
            return False
        if raw.strip().lower() == "any":
            return True
        # comma-separated string
        try:
            return chat_id in {int(x.strip()) for x in raw.split(",") if x.strip()}
        except ValueError:
            return False
    if isinstance(raw, list):
        if not raw:  # пустой список = пускать нельзя
            return False
        return chat_id in raw
    return False


def html_escape(s: str) -> str:
    """Minimal HTML escape for Telegram ParseMode.HTML."""
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def split_text(s: str, max_len: int = 3800) -> list[str]:
    """Telegram message limit is 4096, leave headroom for formatting."""
    if len(s) <= max_len:
        return [s]
    out = []
    while s:
        if len(s) <= max_len:
            out.append(s)
            break
        # Try to break on a newline
        cut = s.rfind("\n", 0, max_len)
        if cut == -1:
            cut = max_len
        else:
            cut += 1
        out.append(s[:cut])
        s = s[cut:]
    return out


# ---- command handlers ----

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    if not allowed_chat(chat.id):
        await update.message.reply_text(
            f"⛔ Этот бот настроен на whitelist. Ваш chat_id: <code>{chat.id}</code>\n"
            f"Добавьте его в <code>telegram_allowed_chat_ids</code> в config.json",
            parse_mode=ParseMode.HTML,
        )
        return
    cfg.init()  # ensure loaded
    h = api().health()
    if not h:
        await update.message.reply_text(
            "⚠️ Не могу достучаться до autrau API. Убедитесь, что сервер запущен:\n"
            "<code>start.bat</code>",
            parse_mode=ParseMode.HTML,
        )
        return
    await update.message.reply_text(
        f"👋 Привет! Я — agent-бот <b>Autrau</b> v{cfg.get('provider', '?')}.\n\n"
        f"<b>Что я умею:</b>\n"
        f"  🎙 Пришли голосовое сообщение → транскрибирую\n"
        f"  🎵 Пришли аудиофайл → транскрибирую\n"
        f"  /help — список команд\n"
        f"  /status — состояние сервера\n"
        f"  /ask <вопрос> — задай вопрос по usability/autrau\n"
        f"\nСервер: <code>{h.get('version', '?')}</code>, "
        f"chat_id: <code>{chat.id}</code>",
        parse_mode=ParseMode.HTML,
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not allowed_chat(update.effective_chat.id):
        return
    await update.message.reply_text(
        "<b>Команды Autrau-бота</b>\n\n"
        "/start — приветствие и состояние\n"
        "/help — эта справка\n"
        "/status — здоровье autrau-сервера\n"
        "/providers — какие ASR-провайдеры доступны\n"
        "/config — текущая конфигурация\n"
        "/lang ru|en|auto — установить язык распознавания\n"
        "/favorites — последние избранные расшифровки\n"
        "/export srt|vtt|json|txt — экспорт последней расшифровки\n"
        "/check — полная диагностика (Python, ffmpeg, git, провайдеры)\n"
        "/update — проверить обновления приложения\n"
        "/ask <вопрос> — спросить что угодно по autrau (агент-режим)\n\n"
        "<b>Медиа:</b>\n"
        "  🎙 голосовое сообщение — авто-транскрипция\n"
        "  🎵 аудиофайл (.mp3/.wav/.ogg/.m4a) — авто-транскрипция\n"
        "  🔗 URL — скачивание через yt-dlp + транскрипция",
        parse_mode=ParseMode.HTML,
    )


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not allowed_chat(update.effective_chat.id):
        return
    h = api().health()
    if not h:
        await update.message.reply_text("❌ autrau-server недоступен на API URL. Запустите start.bat.")
        return
    cfg_now = api().config() or {}
    upd_state = (api()._request("/api/updates/state") or [0, None])[1] or {}
    avail = upd_state.get("available", False)
    text = (
        f"📊 <b>Autrau status</b>\n\n"
        f"  Server: <code>{h.get('version', '?')}</code>\n"
        f"  Python OK: {'✅' if h.get('python_ok') else '❌'}\n"
        f"  Loaded: {h.get('loaded') or '—'}\n\n"
        f"<b>Active config:</b>\n"
        f"  provider: <code>{cfg_now.get('provider', '?')}</code>\n"
        f"  model: <code>{cfg_now.get('model', '?')}</code>\n"
        f"  language: <code>{cfg_now.get('language', '?')}</code>\n"
        f"  translate→EN: {'✅' if cfg_now.get('translate_to_en') else '❌'}\n\n"
        f"<b>Update:</b> {'🆕 available' if avail else '✅ up to date'}"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def cmd_providers(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not allowed_chat(update.effective_chat.id):
        return
    provs = api().providers()
    if not provs:
        await update.message.reply_text("❌ Не могу получить /api/providers")
        return
    lines = ["🧠 <b>Провайдеры ASR</b>\n"]
    for p in provs:
        ok = "✅" if p.get("installed") else "❌"
        active = " ⭐" if p.get("active") else ""
        lines.append(
            f"  {ok} <code>{p.get('name')}</code>{active} — {html_escape(p.get('display_name', ''))}\n"
        )
        if p.get("reason") and not p.get("installed"):
            lines.append(f"     ↳ {html_escape(p['reason'])}\n")
    await update.message.reply_text("".join(lines), parse_mode=ParseMode.HTML)


async def cmd_config(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not allowed_chat(update.effective_chat.id):
        return
    c = api().config()
    if not c:
        await update.message.reply_text("❌ Не могу получить /api/config")
        return
    lines = ["⚙️ <b>Autrau config</b>\n"]
    for k, v in c.items():
        v_str = str(v) if not isinstance(v, (dict, list)) else json.dumps(v, ensure_ascii=False)
        if len(v_str) > 80:
            v_str = v_str[:77] + "..."
        lines.append(f"  <code>{k}</code> = <code>{html_escape(v_str)}</code>\n")
    await update.message.reply_text("".join(lines), parse_mode=ParseMode.HTML)


async def cmd_lang(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not allowed_chat(update.effective_chat.id):
        return
    args = context.args or []
    if not args:
        st = get_state(update.effective_chat.id)
        await update.message.reply_text(f"Текущий язык: <code>{st.language}</code>\n"
                                        f"Установить: <code>/lang ru</code>, <code>/lang en</code>, <code>/lang auto</code>",
                                        parse_mode=ParseMode.HTML)
        return
    new = args[0].lower()
    if new not in ("ru", "en", "auto", "de", "fr", "es"):
        await update.message.reply_text("⚠ Поддерживаю: ru, en, auto, de, fr, es")
        return
    st = get_state(update.effective_chat.id)
    st.language = new
    await update.message.reply_text(f"✅ Язык: <code>{new}</code>", parse_mode=ParseMode.HTML)


async def cmd_favorites(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not allowed_chat(update.effective_chat.id):
        return
    items = api().transcripts() or []
    favs = [t for t in items if t.get("favorite")]
    if not favs:
        await update.message.reply_text("⭐ Избранных расшифровок нет. Поставьте ★ в UI.")
        return
    lines = [f"⭐ <b>Избранные расшифровки</b> ({len(favs)})\n"]
    for t in favs[:20]:
        name = t.get("name", "")
        size_kb = t.get("size_kb", 0)
        lines.append(f"  • <code>{html_escape(name)}</code> ({size_kb:.0f} KB)\n")
    await update.message.reply_text("".join(lines), parse_mode=ParseMode.HTML)


async def cmd_export(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not allowed_chat(update.effective_chat.id):
        return
    args = context.args or []
    if not args:
        await update.message.reply_text("Формат: <code>/export srt|vtt|json|txt</code>", parse_mode=ParseMode.HTML)
        return
    fmt = args[0].lower()
    if fmt not in ("srt", "vtt", "json", "txt"):
        await update.message.reply_text("⚠ Поддерживаю: srt, vtt, json, txt")
        return
    st = get_state(update.effective_chat.id)
    if not st.last_file:
        await update.message.reply_text("⚠ Сначала транскрибируйте файл — пришлите голосовое или аудио.")
        return
    # Имя в API содержит .txt суффикс (так save_transcript сохраняет)
    name = st.last_file if st.last_file.endswith(".txt") else st.last_file + ".txt"
    code, body = api().export(name, fmt)
    if code != 200 or isinstance(body, str):
        await update.message.reply_text(f"❌ Export {fmt}: {code}\n{body if isinstance(body, str) else 'binary'}")
        return
    # Send as document
    await update.message.reply_document(
        document=body,
        filename=name.replace(".txt", f".{fmt}"),
        caption=f"📤 Экспорт {fmt}",
    )


async def cmd_check(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Run full diagnostic — same as `python -m tools.check`."""
    if not allowed_chat(update.effective_chat.id):
        return
    await update.message.reply_text("🔍 Запускаю диагностику…")
    report = check.run_full_check()
    lines = ["🔍 <b>Диагностика autrau</b>\n"]
    py = report["python"]
    lines.append(f"  Python {py['version']}: {'✅' if py['ok'] else '❌ ' + py.get('hint', '')}\n")
    ff = report["ffmpeg"]
    if ff["ok"]:
        lines.append(f"  ffmpeg: ✅ ({ff['version'][:50]})\n")
    else:
        lines.append(f"  ffmpeg: ❌ {ff.get('hint', '')}\n")
    deps = report["deps"]
    lines.append(f"  Зависимости: {'✅' if deps['ok'] else '❌ ' + ','.join(deps.get('missing', []))}\n")
    git = report["git"]
    if git["ok"]:
        lines.append(f"  git: ✅ branch={git['branch']} dirty={git.get('dirty')}\n")
    else:
        lines.append(f"  git: ❌ {git.get('hint', '')}\n")
    upd_info = report.get("app_update", {})
    if upd_info.get("has_update"):
        lines.append(f"  🆕 Update available: отстаём на {upd_info['behind_by']} коммитов\n")
    else:
        lines.append(f"  Updates: ✅ up to date\n")
    lines.append("\n<b>Провайдеры:</b>\n")
    for p in report["providers"]:
        st = "✅" if p["installed"] else "❌"
        lines.append(f"  {st} {html_escape(p['display'])}")
        if not p["installed"]:
            lines.append(f"     ↳ {html_escape(p['reason'])}")
        lines.append("\n")
    text = "".join(lines)
    for chunk in split_text(text):
        await update.message.reply_text(chunk, parse_mode=ParseMode.HTML)


async def cmd_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not allowed_chat(update.effective_chat.id):
        return
    code, body = api()._request("/api/updates/state")
    if code != 200 or not isinstance(body, dict):
        await update.message.reply_text("❌ Не могу получить /api/updates/state")
        return
    if body.get("available"):
        await update.message.reply_text(
            f"🆕 Доступно обновление: <code>{body['latest_version']}</code>\n"
            f"Сейчас: <code>{body['current_version']}</code>\n\n"
            f"Применить: <code>update.bat</code> или в UI вкладка «🔄 Обновления».",
            parse_mode=ParseMode.HTML,
        )
    else:
        await update.message.reply_text(
            f"✅ Уже актуальная версия: <code>{body.get('current_version', '?')}</code>",
            parse_mode=ParseMode.HTML,
        )


# ---- agent mode ----

# Knowledge base: heuristic Q&A for common autrau usability questions
FAQ = [
    (r"(как|how).*(установить|install).*argos",
     "📥 Установка Argos (локальный переводчик EN↔RU, ~336 МБ):\n\n"
     "  1. В UI: шестерёнка → «3.5 🌐 Перевод» → «📥 Установить Argos»\n"
     "  2. Или в терминале:\n"
     "     <code>pip install argostranslate langdetect</code>\n"
     "     <code>py -3.13 -c \"from argostranslate import package; package.update_package_index(); "
     "[package.install_available_packages(p) for p in package.get_available_packages()]\"</code>"),
    (r"(как|how).*(установить|install).*parakeet.*onnx",
     "📥 Установка Parakeet v3 (ONNX/DirectML, без CUDA):\n\n"
     "  <code>pip install onnx-asr[hub] onnxruntime-directml</code>\n\n"
     "Затем в UI: провайдеры → Parakeet v3 (ONNX) → «⬇ Установить»."),
    (r"(как|how).*использовать.*youtube|yt|yt-dlp",
     "🎬 YouTube → транскрипция:\n\n"
     "  • UI: разверните «🔗 Или вставьте URL» в секции загрузки\n"
     "  • CLI: <code>python -m autrau.cli transcribe URL</code> (planned)\n"
     "  • API: <code>POST /api/yt-dlp {\"url\": \"...\"}</code> (SSE stream)"),
    (r"(как|how).*(захватить|capture|записать).*(системн|system|звук|sound)",
     "🔊 Системный звук (loopback):\n\n"
     "  • UI: разверните «🔊 Или захватить системный звук»\n"
     "  • API: <code>GET /api/system-audio/devices</code> → выбрать → "
     "<code>POST /api/system-audio/start</code> → ждать → <code>POST /api/system-audio/stop</code>"),
    (r"(медленн|slow|тормоз|долго|hang)",
     "🐌 Тормозит распознавание? Возможные причины:\n\n"
     "  1. Провайдер: parakeet-onnx на DirectML быстрее faster-whisper на CPU\n"
     "  2. Модель: large-v3 → small (10x быстрее, точность -5%)\n"
     "  3. beam_size: 5 → 1 (быстрее, точность -2%)\n"
     "  4. compute_type: auto → int8 (на CPU быстрее)\n\n"
     "Покажи текущую конфигурацию: <code>/config</code>"),
    (r"(не\s+работает|не\s+транскрибирует|error|ошибка|fail)",
     "❌ Не работает? Попробуй:\n\n"
     "  1. <code>/check</code> — диагностика (Python, ffmpeg, провайдеры)\n"
     "  2. <code>/status</code> — состояние сервера\n"
     "  3. <code>/providers</code> — какие ASR доступны\n"
     "  4. Если провайдер <code>installed=false</code> — поставь через UI\n"
     "  5. <code>autrau-server.out.log</code> — последние 30 строк содержат подсказку"),
    (r"(обнов|update|новая версия|version)",
     "🔄 Обновления:\n\n"
     "  • <code>/update</code> — проверить\n"
     "  • Применить: <code>update.bat</code> (git pull + pip upgrade)\n"
     "  • Auto-update: в UI шестерёнка → «Автоматически обновлять приложение»"),
    (r"(ffmpeg|видео|video|mp4|mkv)",
     "🎬 Видео (mp4/mkv/mov): autrau автоматически извлечёт аудио через ffmpeg.\n\n"
     "  Если не работает: <code>winget install Gyan.FFmpeg</code> и перезапустите терминал."),
    (r"(провайдер|provider|модель|model).*(выбрать|switch|сменить|change)",
     "🎛 Смена провайдера/модели:\n\n"
     "  • UI: верхняя панель → «Провайдер/Модель»\n"
     "  • API: <code>POST /api/config {\"provider\": \"parakeet-onnx\", \"model\": \"parakeet-tdt-0.6b-v3\"}</code>"),
]


def agent_answer(question: str) -> str | None:
    """Heuristic: return answer if question matches a FAQ pattern, else None."""
    import re
    q = question.lower()
    for pat, ans in FAQ:
        if re.search(pat, q):
            return ans
    return None


async def cmd_ask(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Agent mode: freeform question → heuristic FAQ + diagnostic + run if needed."""
    if not allowed_chat(update.effective_chat.id):
        return
    question = " ".join(context.args or [])
    if not question:
        await update.message.reply_text(
            "🤖 <b>Агент-режим</b>\n\n"
            "Спроси что угодно про autrau. Примеры:\n"
            "  <code>/ask как установить Argos?</code>\n"
            "  <code>/ask медленно распознаёт</code>\n"
            "  <code>/ask не работает перевод</code>\n"
            "  <code>/ask как обновить</code>\n"
            "  <code>/ask какие провайдеры</code>",
            parse_mode=ParseMode.HTML,
        )
        return
    # 1) Try FAQ
    ans = agent_answer(question)
    if ans:
        for chunk in split_text(ans):
            await update.message.reply_text(chunk, parse_mode=ParseMode.HTML)
        return
    # 2) Generic: suggest /check
    await update.message.reply_text(
        f"🤔 Не знаю ответа на «{html_escape(question[:60])}».\n\n"
        f"Попробуй:\n"
        f"  <code>/check</code> — диагностика системы\n"
        f"  <code>/status</code> — состояние сервера\n"
        f"  <code>/providers</code> — какие ASR\n"
        f"  <code>/config</code> — текущая конфигурация",
        parse_mode=ParseMode.HTML,
    )


async def handle_freeform_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """If user just types a question (no command), route to agent."""
    if not allowed_chat(update.effective_chat.id):
        return
    text = (update.message.text or "").strip()
    if not text or text.startswith("/"):
        return  # not a question
    # Heuristic: if it has '?' or starts with question word, treat as /ask
    if "?" in text or text.lower().split()[0] in (
        "как", "почему", "зачем", "где", "когда", "что", "какой", "какая", "какие",
        "how", "why", "what", "where", "when", "which",
    ):
        context.args = text.split()
        await cmd_ask(update, context)


# ---- media handlers ----

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Voice message → download .ogg → transcribe via autrau."""
    if not allowed_chat(update.effective_chat.id):
        return
    voice = update.message.voice
    if not voice:
        return
    if voice.file_size and voice.file_size > _MAX_AUDIO_MB * 1024 * 1024:
        await update.message.reply_text(f"⚠ Файл больше {_MAX_AUDIO_MB} МБ (Telegram Bot API лимит). "
                                        f"Отправь как аудиофайл или разбей на части.")
        return
    st = get_state(update.effective_chat.id)
    await update.message.reply_text("🎙 Скачиваю голосовое сообщение…")
    with tempfile.TemporaryDirectory() as tmp:
        ogg = Path(tmp) / f"voice_{update.message.message_id}.ogg"
        try:
            tg_file = await voice.get_file()
            await tg_file.download_to_drive(str(ogg))
        except Exception as e:
            await update.message.reply_text(f"❌ Скачивание: {e}")
            return
        # Convert ogg → wav via ffmpeg (autrau accepts ogg too, but wav is universal)
        wav = Path(tmp) / f"voice_{update.message.message_id}.wav"
        if shutil.which("ffmpeg"):
            r = subprocess.run(
                ["ffmpeg", "-y", "-i", str(ogg), "-ar", "16000", "-ac", "1", "-f", "wav", str(wav)],
                capture_output=True, text=True, timeout=60,
            )
            if r.returncode != 0:
                # Fall back to ogg
                audio = ogg
            else:
                audio = wav
        else:
            audio = ogg
        await _run_transcribe(update, context, audio, st, kind="voice")


async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Audio file (mp3/wav/m4a) → transcribe."""
    if not allowed_chat(update.effective_chat.id):
        return
    audio_msg = update.message.audio or update.message.document
    if not audio_msg:
        return
    if hasattr(audio_msg, "file_size") and audio_msg.file_size and audio_msg.file_size > _MAX_AUDIO_MB * 1024 * 1024:
        await update.message.reply_text(f"⚠ Файл больше {_MAX_AUDIO_MB} МБ. Сожмите или разбейте.")
        return
    st = get_state(update.effective_chat.id)
    fname = getattr(audio_msg, "file_name", None) or f"audio_{update.message.message_id}"
    await update.message.reply_text(f"📥 Скачиваю {fname}…")
    with tempfile.TemporaryDirectory() as tmp:
        local = Path(tmp) / fname
        try:
            tg_file = await audio_msg.get_file()
            await tg_file.download_to_drive(str(local))
        except Exception as e:
            await update.message.reply_text(f"❌ Скачивание: {e}")
            return
        await _run_transcribe(update, context, local, st, kind="audio")


async def _run_transcribe(update: Update, context: ContextTypes.DEFAULT_TYPE,
                          audio_path: Path, st: ChatState, kind: str) -> None:
    """Run /transcribe, stream progress, return final text + translation."""
    chat = update.effective_chat
    progress_msg = await update.message.reply_text(f"⏳ Транскрибирую {kind}… 0%")

    last_pct = [0]

    def on_progress(percent: int, payload: dict) -> None:
        last_pct[0] = percent
        # Update message every 10% to avoid Telegram rate limits
        if percent - last_pct[0] < 10 and percent != 100:
            return

    # Use a thread to not block the event loop
    import asyncio
    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(
            None,
            lambda: api().transcribe(audio_path, language=st.language, on_progress=on_progress),
        )
    except Exception as e:
        await progress_msg.edit_text(f"❌ Ошибка: {e}")
        return
    if not result:
        await progress_msg.edit_text("❌ Пустой ответ от autrau")
        return
    if result.get("error"):
        await progress_msg.edit_text(f"❌ {result['error']}")
        return
    text = result.get("text", "").strip()
    translation = result.get("translation", "").strip()
    info = result.get("info", {})
    fname = result.get("file", "")

    # Save state for /export
    st.last_file = fname
    st.last_text = text
    st.last_translation = translation

    # Build reply
    lines = [
        f"✅ <b>Готово</b> ({info.get('provider', '?')}/{info.get('model', '?')}, "
        f"{info.get('language', '?')}, {info.get('duration', 0):.1f}s)\n\n"
        f"📝 <b>Текст:</b>\n{html_escape(text)}"
    ]
    if translation:
        lines.append(f"\n\n🇬🇧 <b>EN:</b>\n{html_escape(translation)}")
    if fname:
        lines.append(f"\n\n📂 <code>{html_escape(fname)}</code> — <code>/export srt|vtt|json|txt</code>")

    full = "".join(lines)
    try:
        await progress_msg.delete()
    except Exception:
        pass
    for chunk in split_text(full):
        await update.message.reply_text(chunk, parse_mode=ParseMode.HTML)


# ---- main ----

def main() -> int:
    if not PTB_AVAILABLE:
        print("ERROR: python-telegram-bot не установлен.", file=sys.stderr)
        print("       pip install 'python-telegram-bot>=20.0,<22.0'", file=sys.stderr)
        return 1

    cfg.init()
    token = os.environ.get("TELEGRAM_BOT_TOKEN") or cfg.get("telegram_bot_token", "")
    if not token:
        print("ERROR: TELEGRAM_BOT_TOKEN не задан.", file=sys.stderr)
        print("       Создайте бота через @BotFather в Telegram, получите токен,", file=sys.stderr)
        print("       и положите его в data/config.json → telegram_bot_token", file=sys.stderr)
        print("       или env TELEGRAM_BOT_TOKEN=...", file=sys.stderr)
        return 1

    log.info("Starting Autrau Telegram bot…")
    log.info("API URL: %s", cfg.get("telegram_api_url") or _API_URL)
    log.info("Whitelist: %s", cfg.get("telegram_allowed_chat_ids", []))

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("providers", cmd_providers))
    app.add_handler(CommandHandler("config", cmd_config))
    app.add_handler(CommandHandler("lang", cmd_lang))
    app.add_handler(CommandHandler("favorites", cmd_favorites))
    app.add_handler(CommandHandler("export", cmd_export))
    app.add_handler(CommandHandler("check", cmd_check))
    app.add_handler(CommandHandler("update", cmd_update))
    app.add_handler(CommandHandler("ask", cmd_ask))
    # Media
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.AUDIO | filters.Document.AUDIO, handle_audio))
    # Freeform text
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_freeform_text))

    log.info("Bot polling started. Press Ctrl+C to stop.")
    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
