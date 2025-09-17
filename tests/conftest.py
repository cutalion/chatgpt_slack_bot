"""Test configuration and path setup for running inside Docker or host."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOT_DIR = ROOT / "bot"
if str(BOT_DIR) not in sys.path:
    sys.path.insert(0, str(BOT_DIR))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
