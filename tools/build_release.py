#!/usr/bin/env python3
"""Build a self-contained native release; run on each target OS."""
import hashlib
import importlib.metadata
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from anki_x import __version__
from anki_x.platforms import system_id
from signing import configured, notarize, sign_windows


def main():
    target, cpu = system_id()
    dist = ROOT / "dist"
    dist.mkdir(exist_ok=True)
    entry = ROOT / "build/entry.py"
    entry.parent.mkdir(exist_ok=True)
    entry.write_text("from anki_x.cli import main\nraise SystemExit(main())\n")
    signing_enabled = configured(sys.platform)
    extra = ["--codesign-identity", os.environ["MACOS_SIGN_IDENTITY"]] if target == "macos" and signing_enabled else []
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--name", "anki-x",
                    "--onedir", "--console", "--paths", str(ROOT), "--collect-all", "textual",
                    "--collect-all", "miniaudio", "--collect-all", "zstandard", "--collect-all", "platformdirs",
                    "--copy-metadata", "anki-x", "--add-data", str(ROOT / "anki_x/assets") + os.pathsep + "anki_x/assets",
                    *extra, str(entry)], cwd=ROOT, check=True)
    payload = dist / "anki-x"
    licenses = payload / "licenses"
    licenses.mkdir(exist_ok=True)
    shutil.copy2(ROOT / "LICENSE", licenses / "anki-x-MIT.txt")
    shutil.copytree(ROOT / "anki_x/assets/licenses", licenses, dirs_exist_ok=True)
    shutil.copy2(ROOT / "anki_x/assets/ankiconnect-source.tar.gz", payload / "ankiconnect-source.tar.gz")
    dependencies = []
    for name in ("textual", "rich", "platformdirs", "portalocker", "miniaudio", "cffi", "zstandard", "psutil", "packaging"):
        distribution = importlib.metadata.distribution(name)
        dependencies.append({"name": name, "version": distribution.version,
                             "license": distribution.metadata.get("License-Expression") or distribution.metadata.get("License")})
        for relative in distribution.files or []:
            if any(part.lower() in ("license", "licenses", "copying") or part.lower().startswith("license.") for part in relative.parts):
                source = distribution.locate_file(relative)
                if source.is_file():
                    shutil.copy2(source, licenses / (name + "-" + source.name))
    (payload / "DEPENDENCIES.json").write_text(json.dumps(dependencies, indent=2))
    shutil.copy2(ROOT / "README.md", payload / "README.md")
    if target == "windows":
        (payload / "Install anki-x.cmd").write_text('@echo off\r\ncd /d "%~dp0"\r\n"anki-x.exe" install\r\nif errorlevel 1 pause\r\n', encoding="utf-8")
        (payload / "Start anki-x.cmd").write_text('@echo off\r\n"%~dp0anki-x.exe"\r\n', encoding="utf-8")
    else:
        name = "Install anki-x.command" if target == "macos" else "install.sh"
        installer = payload / name
        installer.write_text('#!/bin/sh\nset -eu\nrelease_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)\n"$release_dir/anki-x" install\n')
        installer.chmod(0o755)
        launcher = payload / ("Start anki-x.command" if target == "macos" else "start.sh")
        launcher.write_text('#!/bin/sh\nrelease_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)\nexec "$release_dir/anki-x"\n')
        launcher.chmod(0o755)
    executable = payload / ("anki-x.exe" if target == "windows" else "anki-x")
    if target == "windows" and signing_enabled:
        for binary in payload.rglob("*"):
            if binary.is_file() and binary.suffix.lower() in (".exe", ".dll", ".pyd"):
                sign_windows(binary)
    subprocess.run([str(executable), "--version"], check=True)
    archive = dist / f"anki-x-{__version__}-{target}-{cpu}.zip"
    # ZipFile preserves executable modes. PyInstaller macOS framework links
    # are dereferenced into files so the same safe extractor works everywhere.
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as output:
        for file in sorted(payload.rglob("*")):
            if file.is_file():
                output.write(file, Path("anki-x") / file.relative_to(payload))
    if target == "macos" and signing_enabled:
        notarize(archive)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    (dist / (archive.name + ".sha256")).write_text(digest + "  " + archive.name + "\n")
    (dist / f"{target}-{cpu}-signing.json").write_text(json.dumps({"platform": target, "architecture": cpu,
         "publisher_signed": signing_enabled, "notarized": signing_enabled if target == "macos" else None}, indent=2))
    print("RELEASE", archive, digest)


if __name__ == "__main__":
    main()
