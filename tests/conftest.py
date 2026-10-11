"""Shared pytest setup: make the qc/ and scripts/ modules importable from the tests."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for folder in ("qc", "scripts"):
    sys.path.insert(0, str(ROOT / folder))
