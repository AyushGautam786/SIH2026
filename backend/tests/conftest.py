"""Makes the backend root importable when tests run from anywhere
(`pytest tests`, `python -m pytest tests`, or an IDE runner)."""
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
