#!/usr/bin/env python3
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix="anki-x-native-") as folder:
    with tarfile.open(root / "anki_x/assets/ankiconnect-source.tar.gz") as archive:
        archive.extractall(folder, filter="data")
    subprocess.run([sys.executable, str(root / "tools/smoke_stale_prediction.py"), "--addon-source",
                    str(Path(folder) / "ankiconnect/plugin"), "--tick-during-submit"], check=True, cwd=root)
