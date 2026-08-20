"""`python -m autrau` → запускает сервер.

Делегирует в `server.py` (который лежит в корне проекта — историческая структура).
"""
import sys
from pathlib import Path

# Добавляем корень проекта в sys.path чтобы `import server` работал
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

if __name__ == "__main__":
    # Запускаем server.py как __main__ — он увидит __name__ == "__main__"
    # и выполнит блок `if __name__ == "__main__":`
    import runpy
    runpy.run_path(str(_PROJECT_ROOT / "server.py"), run_name="__main__")
