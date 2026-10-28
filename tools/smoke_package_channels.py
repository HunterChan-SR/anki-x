#!/usr/bin/env python3
"""Exercise a packed npm launcher with the just-built native ZIP, offline."""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from anki_x import __version__
from anki_x.platforms import system_id

subprocess.run([sys.executable, str(ROOT / "tools/prepare_channels.py"), "--assets", str(ROOT / "dist"),
                "--output", str(ROOT / "build/channels"), "--partial"], check=True)
npm = "npm.cmd" if os.name == "nt" else "npm"
package = ROOT / "build/channels/npm"
subprocess.run([npm, "ci", "--ignore-scripts", "--no-audit"], cwd=package, check=True)
result = subprocess.check_output([npm, "pack", "--json", "--ignore-scripts"], cwd=package, text=True)
archive = package / json.loads(result)[0]["filename"]
system, cpu = system_id()
with tempfile.TemporaryDirectory(prefix="anki-x-packages-") as folder:
    root = Path(folder)
    env = dict(os.environ, ANKI_X_HOME=str(root / "user"), ANKI_X_NPM_CACHE=str(root / "cache"))
    subprocess.run([npm, "install", "--prefix", str(root / "npm"), "--ignore-scripts", "--no-audit", str(archive)], check=True, env=env)
    installed = root / "npm/node_modules/anki-x"
    # Use the actual packed launcher's download/cache/extraction code with a
    # local fixture, so branch CI never depends on unpublished GitHub assets.
    script = """const fs=require('node:fs/promises');
const {ensureRuntime}=require('./lib/runtime.cjs');
ensureRuntime(require('./manifest.json'), {download:()=>fs.readFile(process.argv[1])}).catch(e=>{console.error(e);process.exitCode=1});"""
    subprocess.run(["node", "-e", script, str(ROOT / f"dist/anki-x-{__version__}-{system}-{cpu}.zip")], cwd=installed, env=env, check=True)
    command = ["node", str(installed / "bin/anki-x.cjs")]
    assert subprocess.check_output([*command, "--version"], env=env, text=True).strip() == __version__
    update = subprocess.check_output([*command, "update"], env=env, text=True, encoding="utf-8")
    assert "npm install -g anki-x@next" in update if "rc" in __version__ else "npm install -g anki-x@latest" in update
    uninstall = subprocess.check_output([*command, "uninstall", "--yes"], env=env, text=True, encoding="utf-8")
    assert "npm uninstall" in uninstall
    assert not (root / "user/data/installation.json").exists()
    print("Packed npm launcher: version, offline cache, upgrade/uninstall ownership passed")
