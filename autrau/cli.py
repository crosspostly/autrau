"""`python -m autrau.cli` → CLI для autrau.

Re-export из `tools.cli` чтобы работал через package namespace.
"""
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from tools import cli as _cli  # noqa: E402

if __name__ == "__main__":
    sys.exit(_cli.main())
