"""Self-update: `git pull` + `pip install -U` for autrau itself.

Model updates are handled per-provider via `provider.check_model_update()`
and `provider.download_model()` (called from the UI/API).
"""
from __future__ import annotations

import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import Callable, Optional

from .check import PROJECT_ROOT, _check_app_update, _check_providers

log = logging.getLogger("autrau.update")


def _run(cmd: list[str], cwd: Path = PROJECT_ROOT, timeout: int = 300) -> dict:
    try:
        proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout)
        return {
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout": (proc.stdout or "")[-2000:],
            "stderr": (proc.stderr or "")[-2000:],
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def current_version() -> str:
    """Текущий HEAD commit (short). 'unknown' если не git."""
    try:
        out = _run(["git", "rev-parse", "--short", "HEAD"], timeout=5)
        if out["ok"] and out.get("stdout"):
            return out["stdout"].strip()
    except Exception:
        pass
    return "unknown"


def latest_version() -> Optional[str]:
    """Latest origin/main commit (short). None если fetch failed."""
    out = _run(["git", "ls-remote", "origin", "main"], timeout=15)
    if not out["ok"]:
        return None
    sha = (out.get("stdout") or "").split("\n")[0].split()[0]
    if not sha:
        return None
    return sha[:7]


def app_pull(on_log: Optional[Callable[[str], None]] = None) -> dict:
    """git pull --ff-only. Returns {ok, summary}."""
    cb = on_log or (lambda m: None)
    cb("git fetch …")
    fetch = _run(["git", "fetch", "--quiet", "origin"])
    if not fetch["ok"]:
        return {"ok": False, "step": "fetch", "detail": fetch}
    cb("git pull --ff-only …")
    pull = _run(["git", "pull", "--ff-only"])
    if not pull["ok"]:
        return {"ok": False, "step": "pull", "detail": pull}
    cb("OK")
    return {"ok": True, "summary": pull["stdout"]}


def deps_upgrade(on_log: Optional[Callable[[str], None]] = None) -> dict:
    cb = on_log or (lambda m: None)
    cb("pip install --upgrade -r requirements.txt …")
    proc = _run([sys.executable, "-m", "pip", "install", "--upgrade", "-r",
                 str(PROJECT_ROOT / "requirements.txt")], timeout=900)
    if not proc["ok"]:
        return {"ok": False, "step": "pip", "detail": proc}
    cb("OK")
    return {"ok": True}


def run_full_update() -> dict:
    """Self-update: pull, upgrade deps, then re-check providers."""
    log_pull = []
    def cb(m): log_pull.append(m)
    pull = app_pull(cb)
    deps = deps_upgrade(cb)
    return {
        "app_pull": pull,
        "deps_upgrade": deps,
        "log": log_pull,
        "providers_after": _check_providers(),
    }


def check_all_updates(
    on_progress: Optional[Callable[[dict], None]] = None,
) -> dict:
    """Used by /api/updates: report app + per-model status.

    `on_progress` is called with a dict: {phase, label, percent, done, total, provider, model}.
    """
    cb = on_progress or (lambda m: None)
    cb({"phase": "app", "label": "проверка обновления приложения …", "percent": 0})
    app = _check_app_update()
    models: list[dict] = []
    try:
        from providers import registry
        # Проверяем только модели, которые реально скачаны на диск:
        # незагруженные ни на что не влияют, а HF-запросы по 20 моделям
        # делают проверку медленной.
        pairs = [(p, m) for p in registry.all() for m in p.info.models
                 if p.is_model_downloaded(m)]
        total = len(pairs)
        for i, (p, m) in enumerate(pairs, 1):
            cb({"phase": "model", "provider": p.info.name, "model": m,
                "done": i, "total": total,
                "label": f"{p.info.name} / {m} …",
                "percent": round(100 * (i - 1) / total) if total else 100})
            info = p.check_model_update(m)
            info["provider"] = p.info.name
            info["display"] = p.info.display_name
            models.append(info)
    except Exception as e:
        models = [{"error": f"providers unavailable: {e}"}]
    cb({"phase": "done", "label": "готово", "percent": 100})
    return {"app": app, "models": models}


# ---- CLI ----

def main() -> int:
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--check", action="store_true", help="only check, don't change")
    p.add_argument("--app", action="store_true", help="update the app (git pull + pip upgrade)")
    args = p.parse_args()

    if args.check or not (args.app):
        report = check_all_updates()
        print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.app:
        out = run_full_update()
        print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
