import sys
from pathlib import Path

# event_tracker and pdl_loader use bare imports
# -> package directory itself must be importable
SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))