#!/usr/bin/env python3
"""Run cross-platform Textual navigation, setup and restart acceptance tests."""
import subprocess
import sys
from pathlib import Path
root = Path(__file__).resolve().parents[1]
raise SystemExit(subprocess.call([sys.executable, "-m", "pytest", "tests/test_app.py", "tests/test_navigation.py", "-q"], cwd=root))
