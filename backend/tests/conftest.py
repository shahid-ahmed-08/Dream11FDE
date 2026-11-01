import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
BACKEND = Path(__file__).resolve().parent.parent

for p in [str(ROOT), str(BACKEND)]:
    if p not in sys.path:
        sys.path.insert(0, p)

