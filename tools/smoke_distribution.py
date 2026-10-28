#!/usr/bin/env python3
"""Install a frozen release in an empty user directory without relying on source."""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
executable = "anki-x.exe" if os.name == "nt" else "anki-x"
payload = ROOT / "dist/anki-x"
with tempfile.TemporaryDirectory(prefix="anki-x-clean-install-") as folder:
    root = Path(folder).resolve()
    env = dict(os.environ, ANKI_X_HOME=str(root / "user"), ANKI_X_BIN_DIR=str(root / "bin"))
    # Do not mutate the real Windows user PATH/Start Menu during smoke tests.
    env["ANKI_X_NO_PATH_UPDATE"] = "1"
    env["ANKI_X_SHORTCUT_DIR"] = str(root / "shortcuts")
    for key in ("PYTHONPATH", "PYTHONHOME", "ANKI_X_LEGACY_HOME", "ANKI_X_STATE_DIR"):
        env.pop(key, None)
    result = subprocess.run([str(payload / executable), "install"], cwd=root, env=env,
                            capture_output=True, text=True, encoding="utf-8", timeout=90)
    if result.returncode:
        raise SystemExit(result.stdout + result.stderr)
    metadata = json.loads((root / "user/data/installation.json").read_text())
    installed = Path(metadata["root"]) / executable
    version = subprocess.check_output([str(installed), "--version"], cwd=root, env=env, text=True, encoding="utf-8").strip()
    paths = json.loads(subprocess.check_output([str(installed), "--json", "paths"], cwd=root, env=env, text=True, encoding="utf-8"))
    assert all(Path(path).resolve().is_relative_to((root / "user").resolve()) for path in paths.values()), paths
    assert (Path(metadata["root"]) / "licenses/anki-x-MIT.txt").exists()
    launcher = metadata["launchers"][0]
    invocation = ["cmd", "/c", launcher, "--version"] if os.name == "nt" else [launcher, "--version"]
    assert subprocess.check_output(invocation, cwd=root, env=env, text=True, encoding="utf-8").strip() == version
    report = {"version": version, "platform": sys.platform, "frozen_install": True,
              "source_independent": True, "user_data_outside_program": True}
    (ROOT / f"dist/{sys.platform}-verification.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
