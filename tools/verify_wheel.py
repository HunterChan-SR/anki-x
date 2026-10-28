#!/usr/bin/env python3
"""Ensure the wheel is self-sufficient for first-run onboarding."""
import sys
import zipfile
from pathlib import Path

directory = Path(sys.argv[1])
wheels = list(directory.glob("*.whl"))
assert len(wheels) == 1, wheels
with zipfile.ZipFile(wheels[0]) as wheel:
    names = set(wheel.namelist())
    for asset in ("ankiconnect-source.tar.gz", "ankiconnect.ankiaddon", "anki-releases.json"):
        assert "anki_x/assets/" + asset in names, asset
    assert any(name.startswith("anki_x/assets/licenses/") for name in names)
    assert any(name.endswith(".mp3") or name.endswith(".wav") for name in names)
    assert not any(".state/" in name or "node_modules/" in name for name in names)
print("Python wheel contains onboarding, audio, licenses and connector source")
