"""OS integration kept outside the application and scheduling model."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from pathlib import Path


def system_id():
    system = platform.system()
    machine = platform.machine().lower()
    cpu = "arm64" if machine in ("arm64", "aarch64") else "x64" if machine in ("x86_64", "amd64") else machine
    return {"Darwin": "macos", "Windows": "windows", "Linux": "linux"}.get(system, system.lower()), cpu


def anki_bases(configured=None):
    candidates = []
    for value in (configured, os.environ.get("ANKI_BASE")):
        if value:
            candidates.append(Path(value).expanduser())
    home = Path.home()
    system, _ = system_id()
    if system == "macos":
        candidates.append(home / "Library/Application Support/Anki2")
    elif system == "windows":
        candidates.append(Path(os.environ.get("APPDATA", home / "AppData/Roaming")) / "Anki2")
    else:
        candidates.extend([Path(os.environ.get("XDG_DATA_HOME", home / ".local/share")) / "Anki2",
                           home / ".var/app/net.ankiweb.Anki/data/Anki2"])
    return list(dict.fromkeys(candidates))


def find_anki(configured=None, data_dir=None):
    system, _ = system_id()
    candidates = [Path(configured).expanduser()] if configured else []
    home = Path.home()
    if system == "macos":
        candidates.extend([Path("/Applications/Anki.app"), home / "Applications/Anki.app"])
    elif system == "windows":
        for root in (Path(os.environ.get("LOCALAPPDATA", home / "AppData/Local")) / "Programs",
                     Path(os.environ.get("PROGRAMFILES", "C:/Program Files"))):
            candidates.append(root / "Anki/anki.exe")
    else:
        for value in (shutil.which("anki"), "/usr/local/share/anki/anki", "/usr/bin/anki"):
            if value:
                candidates.append(Path(value))
        if data_dir:
            candidates.extend(sorted((Path(data_dir) / "dependencies").glob("anki-*/anki"), reverse=True))
    return next((p for p in candidates if p.exists()), None)


def launch_command(executable, base=None, profile=None):
    system, _ = system_id()
    args = []
    if base:
        args += ["-b", str(base)]
    if profile:
        args += ["-p", str(profile)]
    if system == "macos" and str(executable).endswith(".app"):
        return ["open", "-g", "-a", str(executable), "--args", *args]
    return [str(executable), *args]


def launch_anki(executable, base=None, profile=None):
    kwargs = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    return subprocess.Popen(launch_command(executable, base, profile), **kwargs)


def open_file(path):
    path = str(Path(path).resolve())
    system, _ = system_id()
    if system == "windows":
        os.startfile(path)
    else:
        subprocess.Popen(["open" if system == "macos" else "xdg-open", path],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
