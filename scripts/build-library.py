#!/usr/bin/env python3
"""Rebuild assets/library.json (thin wrapper around clemtock.library.rebuild)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from clemtock.library import rebuild  # noqa: E402

if __name__ == "__main__":
    print(rebuild())
