#!/usr/bin/env python3
"""
CLI: seed the vision store and demo evidence packages for the steward
workstation (Iteration 9). Run from the repo root:

    .venv/bin/python scripts/seed_vision_demo.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import vision_store
from src.vision import demo
from src.vision import evidence as vision_evidence


if __name__ == "__main__":
    result = demo.seed()
    print(f"[demo] {len(result['incidents'])} incidents -> {vision_store.VISION_INCIDENTS_JSON}")
    print(f"[demo] {len(result['packages'])} evidence packages -> {vision_evidence.INCIDENTS_DIR}")