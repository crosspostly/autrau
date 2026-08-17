"""Diagnostics: Python, ffmpeg, deps, git, app updates, model updates.

Pure stdlib where possible (no fastapi/uvicorn needed at check time).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ---- public API ----

def run_full_check() -> dict[str, Any]:
    """Run all checks, return a structured report."""
    return {
        "python": _check_python(),
        "ffmpeg": _check_ffmpeg(),
        "deps": _check_deps(),
        "git": _check_git(),
        "app_update": _check_app_update(),
        "providers": _check_providers(),
    }


def _check_python() -> dict:
    v = sys.version_info
    ok = (v.major, v.minor) >= (3, 10)
    return {
        "ok": ok,
        "version": f"{v.major}.{v.minor}.{v.micro}",
        "path": sys.executable,
        "need": "Python ≥ 3.10",
        "hint": "Скачайте с https://www.python.org/downloads/" if not ok else "",
    }


def _check_ffmpeg() -> dict:
    path = shutil.which("ffmpeg")
    if not path:
        return {"ok": False, "version": None, "path": None,
                "hint": "winget install Gyan.FFmpeg"}
    try:
        out = subprocess.run([path, "-version"], capture_output=True, text=True, timeout=5)
        ver = (out.stdout or "").splitlines()[0] if out.stdout else ""
    except Exception as e:
        ver = f"ошибка: {e}"
    return {"ok": True, "version": ver, "path": path}


def _check_deps() -> dict:
    """Required runtime deps."""
    required = ["fastapi", "uvicorn", "multipart"]
    missing = []
    for mod in required:
        try:
            __import__(mod)
        except ImportError:
            missing.append(mod)
    return {
        "ok": not missing,
        "missing": missing,
        "hint": "pip install -r requirements.txt" if missing else "",
    }


def _check_git() -> dict:
    path = shutil.which("git")
    if not path:
        return {"ok": False, "hint": "Git не найден в PATH", "path": None}
    try:
        out = subprocess.run(["git", "-C", str(PROJECT_ROOT), "rev-parse", "--abbrev-ref", "HEAD"],
                             capture_output=True, text=True, timeout=5)
        branch = (out.stdout or "").strip() or "(unknown)"
        out2 = subprocess.run(["git", "-C", str(PROJECT_ROOT), "remote", "get-url", "origin"],
                              capture_output=True, text=True, timeout=5)
        remote = (out2.stdout or "").strip()
        out3 = subprocess.run(["git", "-C", str(PROJECT_ROOT), "status", "--porcelain"],
                              capture_output=True, text=True, timeout=5)
        dirty = bool((out3.stdout or "").strip())
        return {"ok": True, "branch": branch, "remote": remote, "dirty": dirty, "path": path}
    except Exception as e:
        return {"ok": False, "hint": str(e), "path": path}


def _check_app_update() -> dict:
    """If git is initialized with origin, look for new commits."""
    info: dict[str, Any] = {"ok": True, "has_update": False}
    try:
        subprocess.run(["git", "-C", str(PROJECT_ROOT), "remote", "get-url", "origin"],
                       capture_output=True, text=True, timeout=5, check=True)
    except Exception:
        info["note"] = "нет origin (это просто локальный клон)"
        return info
    try:
        # Fetch quietly; tolerate network failure.
        subprocess.run(["git", "-C", str(PROJECT_ROOT), "fetch", "--quiet", "origin"],
                       capture_output=True, text=True, timeout=30)
        out = subprocess.run(
            ["git", "-C", str(PROJECT_ROOT), "rev-list", "--left-right", "--count",
             "HEAD...@{u}"],
            capture_output=True, text=True, timeout=10,
        )
        if out.returncode == 0 and out.stdout.strip():
            ahead, behind = (out.stdout.strip().split("\t") + ["0", "0"])[:2]
            behind_i = int(behind)
            info["behind_by"] = behind_i
            info["ahead_by"] = int(ahead)
            info["has_update"] = behind_i > 0
    except Exception as e:
        info["error"] = str(e)
    return info


def _check_providers() -> list[dict]:
    """For each known provider, report installed + active model status."""
    from providers import registry
    out = []
    for p in registry.all():
        avail, why = p.is_available()
        item = {
            "name": p.info.name,
            "display": p.info.display_name,
            "installed": avail,
            "reason": why,
            "requires_gpu": p.info.requires_gpu,
            "default_model": p.info.default_model,
            "models": [
                {"name": m, "downloaded": p.is_model_downloaded(m)}
                for m in p.info.models
            ],
        }
        out.append(item)
    return out


# ---- CLI ----

def main() -> int:
    report = run_full_check()
    print(json.dumps(report, ensure_ascii=False, indent=2))

    # Concise summary
    py = report["python"]
    print(f"\nPython {py['version']} - {'OK' if py['ok'] else 'NEED UPGRADE'}")
    if report['ffmpeg']['ok']:
        print(f"ffmpeg   - OK ({report['ffmpeg']['version'][:60]})")
    else:
        print(f"ffmpeg   - MISSING (install: winget install Gyan.FFmpeg)")
    if report['deps']['ok']:
        print(f"deps     - OK")
    else:
        print(f"deps     - MISSING: {','.join(report['deps']['missing'])}")
    print(f"git      - {'OK' if report['git']['ok'] else 'MISSING'}")
    upd = report.get("app_update", {})
    if upd.get("has_update"):
        print(f"⚠️  Есть обновления: отстаём на {upd['behind_by']} коммитов. Запустите update.bat")
    for p in report["providers"]:
        status = "✅" if p["installed"] else "❌"
        print(f"  {status} {p['display']}")
        if not p["installed"]:
            print(f"      ↳ {p['reason']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
