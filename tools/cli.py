"""Autrau CLI — use autrau from the terminal.

Sub-commands:
    transcribe <file>     — transcribe a single file
    batch <dir>           — batch transcribe all audio files in a directory
    providers             — list available providers
    models --provider X   — list models for a provider
    status                — server status + config summary
    health                — quick health check (server up?)

Requires the autrau server running on http://127.0.0.1:8000 (default).
Override with AUTRAU_API env var: `AUTRAU_API=http://localhost:9000 python -m autrau.cli status`.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

API = os.environ.get("AUTRAU_API", "http://127.0.0.1:8000")

# ---- helpers ----

def _die(msg: str, code: int = 1) -> None:
    print(f"❌ {msg}", file=sys.stderr)
    sys.exit(code)


def _http_get_json(path: str) -> Any:
    url = f"{API}{path}"
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.URLError as e:
        _die(f"Server unreachable at {API} ({e.reason}). Запусти `start.bat` или `python server.py`.")
    except urllib.error.HTTPError as e:
        _die(f"HTTP {e.code} GET {url}: {e.read().decode('utf-8', errors='replace')[:200]}")


def _build_multipart(file_path: Path, fields: dict[str, str], boundary: str | None = None) -> tuple[bytes, str]:
    """Build multipart/form-data body. Returns (body, content_type)."""
    if boundary is None:
        boundary = "----AutrauCli" + str(int(time.time() * 1000))
    parts: list[bytes] = []
    for k, v in fields.items():
        parts.append(f"--{boundary}\r\n".encode())
        parts.append(f'Content-Disposition: form-data; name="{k}"\r\n\r\n'.encode())
        parts.append(v.encode("utf-8"))
        parts.append(b"\r\n")
    # file
    parts.append(f"--{boundary}\r\n".encode())
    parts.append(
        f'Content-Disposition: form-data; name="file"; filename="{file_path.name}"\r\n'
        f"Content-Type: application/octet-stream\r\n\r\n".encode()
    )
    parts.append(file_path.read_bytes())
    parts.append(b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def _parse_sse_stream(response) -> dict:
    """Parse /transcribe SSE stream, return final 'done' payload."""
    final: dict | None = None
    last_percent = -1
    for raw_line in response:
        line = raw_line.decode("utf-8", errors="replace").rstrip("\r\n")
        if not line.startswith("data: "):
            continue
        try:
            evt = json.loads(line[6:])
        except json.JSONDecodeError:
            continue
        etype = evt.get("type")
        percent = evt.get("percent", 0)
        payload = evt.get("payload")
        if etype == "progress":
            if percent != last_percent and percent % 10 == 0:
                # Show progress: 10/20/30/.../100
                print(f"  ... {percent}%", file=sys.stderr)
                last_percent = percent
        elif etype == "done":
            final = payload if isinstance(payload, dict) else {}
        elif etype == "error":
            _die(f"Server error: {payload}")
    if final is None:
        _die("Stream ended without 'done' event")
    return final


# ---- commands ----

def cmd_transcribe(args: argparse.Namespace) -> int:
    path = Path(args.path)
    if not path.is_file():
        _die(f"Файл не найден: {path}")

    fields = {"language": args.language}
    if args.provider:
        fields["provider"] = args.provider
    if args.model:
        fields["model"] = args.model
    if args.device:
        fields["device"] = args.device

    body, ctype = _build_multipart(path, fields)
    req = urllib.request.Request(
        f"{API}/transcribe",
        data=body,
        headers={"Content-Type": ctype},
        method="POST",
    )
    print(f"🎙 Транскрибирую {path.name} ({path.stat().st_size} байт) …", file=sys.stderr)
    try:
        with urllib.request.urlopen(req, timeout=3600) as r:
            result = _parse_sse_stream(r)
    except urllib.error.HTTPError as e:
        _die(f"HTTP {e.code}: {e.read().decode('utf-8', errors='replace')[:300]}")
    except urllib.error.URLError as e:
        _die(f"Server unreachable: {e.reason}")

    text = (result.get("text") or "").strip()
    if not text:
        _die("Сервер вернул пустой результат")

    # Save
    if args.output:
        out = Path(args.output)
    else:
        # default: stdout (если --output не указан)
        if args.format == "txt":
            print(text)
            return 0
        # if format != txt без --output — error
        _die(f"--format={args.format} требует --output")

    out.parent.mkdir(parents=True, exist_ok=True)
    if args.format == "txt":
        out.write_text(text, encoding="utf-8")
    elif args.format in ("srt", "vtt", "json"):
        # request export from server
        if not result.get("file"):
            _die("Сервер не вернул имя файла — не могу запросить экспорт")
        server_name = result["file"]
        url = f"{API}/api/transcripts/{urllib.parse.quote(server_name)}/export?format={args.format}"
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                out.write_bytes(r.read())
        except urllib.error.HTTPError as e:
            _die(f"Export failed: HTTP {e.code}")
    print(f"✅ Сохранено: {out}", file=sys.stderr)
    # Summary to stderr (not stdout — stdout = transcript text)
    print(f"📝 {len(text)} символов, {len(result.get('segments', []))} сегментов", file=sys.stderr)
    if result.get("translation"):
        print(f"🌐 Translation: {len(result['translation'])} символов ({result.get('translation_provider', '?')})", file=sys.stderr)
    return 0


def cmd_batch(args: argparse.Namespace) -> int:
    path = Path(args.path)
    if not path.is_dir():
        _die(f"Директория не найдена: {path}")

    pattern = args.pattern
    files: list[Path] = []
    if args.recursive:
        files = [p for p in path.rglob("*") if p.is_file() and _matches(p.name, pattern)]
    else:
        files = [p for p in path.iterdir() if p.is_file() and _matches(p.name, pattern)]

    if not files:
        print(f"❌ Не найдено файлов по паттерну '{pattern}' в {path}", file=sys.stderr)
        return 1

    print(f"📁 Найдено {len(files)} файл(ов)", file=sys.stderr)
    out_dir = Path(args.output) if args.output else path / "transcripts"
    out_dir.mkdir(parents=True, exist_ok=True)
    ok = 0
    fail = 0
    for i, f in enumerate(files, 1):
        print(f"\n[{i}/{len(files)}] {f.name}", file=sys.stderr)
        # build args namespace for transcribe
        t_args = argparse.Namespace(
            path=str(f),
            language=args.language,
            provider=None, model=None, device=None,
            output=str(out_dir / (f.stem + ".txt")),
            format="txt",
        )
        try:
            cmd_transcribe(t_args)
            ok += 1
        except SystemExit as e:
            if e.code != 0:
                fail += 1
                print(f"  ❌ failed", file=sys.stderr)
    print(f"\n📊 Готово: {ok} ок, {fail} fail", file=sys.stderr)
    return 0 if fail == 0 else 1


def _matches(name: str, pattern: str) -> bool:
    """Match name against brace-expansion pattern like '*.{mp3,wav}'."""
    if "{" in pattern:
        head, rest = pattern.split("{", 1)
        opts, tail = rest.split("}", 1)
        for opt in opts.split(","):
            if name.startswith(head) and name[len(head):].endswith(tail) and opt in name:
                return True
        return False
    # simple glob-ish
    return bool(re.match(pattern.replace(".", r"\.").replace("*", ".*"), name))


def cmd_providers(args: argparse.Namespace) -> int:
    data = _http_get_json("/api/providers")
    providers = data.get("providers", [])
    active = data.get("active", {})
    print(f"{'Name':<22} {'Display':<30} {'Available':<10} {'Default':<10} {'Active'}")
    print("─" * 90)
    for p in providers:
        name = p.get("name", "?")
        is_active = active.get("name") == name
        avail = "✓" if p.get("available") else "✗"
        default = "✓" if p.get("default_model") and active.get("model") == p.get("default_model") else ""
        print(f"{name:<22} {p.get('display_name', '')[:30]:<30} {avail:<10} {default:<10} {'★' if is_active else ''}")
    return 0


def cmd_models(args: argparse.Namespace) -> int:
    data = _http_get_json("/api/providers")
    for p in data.get("providers", []):
        if p.get("name") == args.provider:
            print(f"Provider: {p.get('display_name', args.provider)}")
            print(f"{'Name':<30} {'Downloaded':<12} {'Size MB':<10} {'Quant'}")
            print("─" * 70)
            for m in p.get("models", []):
                downloaded = "✓" if m.get("downloaded") else "—"
                size = m.get("size_mb", "?")
                quant = m.get("quant", "")
                print(f"{m.get('name', '?'):<30} {downloaded:<12} {size:<10} {quant}")
            return 0
    _die(f"Провайдер '{args.provider}' не найден")


def cmd_status(args: argparse.Namespace) -> int:
    health = _http_get_json("/health")
    config = _http_get_json("/api/config")
    print(f"🟢 Server: {API}")
    print(f"   version:  {health.get('version', '?')}")
    print(f"   loaded:   {health.get('loaded', '?')}")
    print()
    print("⚙️ Config:")
    for k in ("provider", "model", "language", "device", "translate_to_en",
              "translation_provider", "cleanup_after_days", "hotkey"):
        if k in config:
            v = config[k]
            print(f"   {k}: {v}")
    return 0


def cmd_health(args: argparse.Namespace) -> int:
    try:
        with urllib.request.urlopen(f"{API}/health", timeout=5) as r:
            data = json.loads(r.read())
        print(f"🟢 {data.get('status', 'ok')} — {data.get('version', '?')}")
        return 0
    except Exception as e:
        print(f"🔴 down — {e}", file=sys.stderr)
        return 1


# ---- main ----

def main() -> int:
    parser = argparse.ArgumentParser(
        prog="autrau",
        description="Autrau CLI — локальный транскрибатор аудио/видео",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
примеры:
  %(prog)s transcribe interview.mp3
  %(prog)s transcribe voice.webm --language en --output out.txt
  %(prog)s batch ./audio/ --pattern "*.{mp3,wav}" --output ./out/
  %(prog)s providers
  %(prog)s models --provider whisper-cpp
  %(prog)s status
""",
    )
    sub = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    # transcribe
    p_t = sub.add_parser("transcribe", help="Транскрибировать один файл")
    p_t.add_argument("path", help="Путь к аудио/видео файлу")
    p_t.add_argument("--language", "-l", default="ru", help="Язык (default: ru)")
    p_t.add_argument("--provider", help="Провайдер (default: из config)")
    p_t.add_argument("--model", help="Модель (default: из config)")
    p_t.add_argument("--device", default="cpu", help="Device (default: cpu)")
    p_t.add_argument("--output", "-o", help="Куда сохранить (default: stdout для txt)")
    p_t.add_argument("--format", choices=["txt", "srt", "vtt", "json"], default="txt",
                     help="Формат экспорта (default: txt)")
    p_t.set_defaults(func=cmd_transcribe)

    # batch
    p_b = sub.add_parser("batch", help="Пакетная обработка директории")
    p_b.add_argument("path", help="Директория с аудио файлами")
    p_b.add_argument("--pattern", default="*.{mp3,wav,m4a,ogg,flac,mp4,mkv,webm}",
                     help="Glob pattern (default: все аудио/видео)")
    p_b.add_argument("--language", "-l", default="ru")
    p_b.add_argument("--output", "-o", help="Директория для результатов (default: <path>/transcripts/)")
    p_b.add_argument("--recursive", "-r", action="store_true", help="Рекурсивно обходить поддиректории")
    p_b.set_defaults(func=cmd_batch)

    # providers
    sub.add_parser("providers", help="Список провайдеров").set_defaults(func=cmd_providers)

    # models
    p_m = sub.add_parser("models", help="Список моделей провайдера")
    p_m.add_argument("--provider", "-p", required=True, help="Имя провайдера")
    p_m.set_defaults(func=cmd_models)

    # status
    sub.add_parser("status", help="Статус сервера + config").set_defaults(func=cmd_status)

    # health
    sub.add_parser("health", help="Быстрая проверка доступности сервера").set_defaults(func=cmd_health)

    args = parser.parse_args()
    return args.func(args) or 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n⚠️ Прервано", file=sys.stderr)
        sys.exit(130)
