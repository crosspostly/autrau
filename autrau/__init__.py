"""Autrau package shim.

`autrau/` as a Python package so that `python -m autrau` and
`python -m autrau.cli` work. Delegates to `tools.cli` and `server.py`.

Структура:
- autrau/__init__.py     (this file)
- autrau/__main__.py     — runs server.py (для `python -m autrau`)
- autrau/cli.py          — re-exports tools.cli (для `python -m autrau.cli`)

Все реальные модули лежат в `tools/`, `providers/`, `server.py` — это историческая
структура проекта, package-обёртка просто делает CLI доступным через `-m autrau`.
"""
__version__ = "1.5.7"
