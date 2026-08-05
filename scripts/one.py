#!/usr/bin/env python3
"""Run one-skills from a source checkout without installation."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from one_skills.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
