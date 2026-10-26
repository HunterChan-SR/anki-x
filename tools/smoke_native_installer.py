#!/usr/bin/env python3
"""Validate the actual native installation entry, using isolated user locations."""
import json
import os
import plistlib
import subprocess
import sys
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
if sys.platform == "win32":
    installer = next((root / "dist").glob("*-setup.exe"))
    with tempfile.TemporaryDirectory(prefix="anki-x-native-install-") as folder:
        path = Path(folder).resolve()
        env = dict(os.environ, ANKI_X_HOME=str(path / "user"), ANKI_X_BIN_DIR=str(path / "bin"),
                   ANKI_X_SHORTCUT_DIR=str(path / "shortcuts"), ANKI_X_NO_PATH_UPDATE="1")
        result = subprocess.run([str(installer), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"], env=env, timeout=120)
        assert result.returncode == 0, result.returncode
        installation = json.loads((path / "user/data/installation.json").read_text())
        command = Path(installation["launchers"][0])
        version = subprocess.check_output(["cmd", "/c", str(command), "--version"], env=env, encoding="utf-8").strip()
        assert version == installation["version"]
        print("PASS Windows setup.exe installed and its command runs without Python.")
elif sys.platform == "darwin":
    dmg = next((root / "dist").glob("*.dmg"))
    with tempfile.TemporaryDirectory(prefix="anki-x-dmg-check-") as folder:
        mount = Path(folder) / "mount"
        mount.mkdir()
        subprocess.run(["hdiutil", "attach", str(dmg), "-readonly", "-nobrowse", "-mountpoint", str(mount)], check=True, capture_output=True)
        try:
            app = mount / "Anki X.app/Contents"
            info = plistlib.loads((app / "Info.plist").read_bytes())
            assert (app / "MacOS" / info["CFBundleExecutable"]).is_file()
            assert (app / "Resources/Start.command").is_file()
            output = subprocess.check_output([str(app / "Resources/runtime/anki-x"), "--version"], text=True).strip()
            assert output == info["CFBundleShortVersionString"]
            print("PASS macOS DMG mounts and contains a working self-contained app.")
        finally:
            subprocess.run(["hdiutil", "detach", str(mount)], check=True, capture_output=True)
else:
    print("Linux install.sh is covered by the frozen distribution installation check.")
