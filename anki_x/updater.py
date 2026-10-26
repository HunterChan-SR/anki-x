"""Versioned user installation, verified updates and local rollback."""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from contextlib import nullcontext
from pathlib import Path

from packaging.version import Version

from . import __version__
from .downloads import download_verified, extract_zip
from .platforms import system_id
from .storage import SessionLock, read_json, write_json

REPOSITORY = "HunterChan-SR/anki-x"


def installation(paths):
    return read_json(paths.data / "installation.json")


def _launcher(paths, root):
    system, _ = system_id()
    if system == "windows":
        bindir = Path(os.environ.get("ANKI_X_BIN_DIR", Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")) / "Programs/anki-x/bin"))
        bindir.mkdir(parents=True, exist_ok=True)
        command = bindir / "anki-x.cmd"
        command.write_text('@echo off\r\nchcp 65001 >nul\r\nrem anki-x managed launcher\r\n"' + str(root / "anki-x.exe") + '" %*\r\n', encoding="utf-8")
        # Update the user's PATH without truncating it through setx.
        import winreg
        if not os.environ.get("ANKI_X_NO_PATH_UPDATE"):
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
                try:
                    current, kind = winreg.QueryValueEx(key, "Path")
                except FileNotFoundError:
                    current, kind = "", winreg.REG_EXPAND_SZ
                if str(bindir).lower() not in [part.lower() for part in current.split(";")]:
                    winreg.SetValueEx(key, "Path", 0, kind, current.rstrip(";") + ";" + str(bindir))
        start = Path(os.environ.get("ANKI_X_SHORTCUT_DIR", Path(os.environ.get("APPDATA", Path.home() / "AppData/Roaming")) / "Microsoft/Windows/Start Menu/Programs"))
        start.mkdir(parents=True, exist_ok=True)
        shortcut = start / "anki-x.cmd"
        shortcut.write_text(command.read_text(), encoding="utf-8")
        return [str(command), str(shortcut)]
    bindir = Path(os.environ.get("ANKI_X_BIN_DIR", Path.home() / ".local/bin"))
    bindir.mkdir(parents=True, exist_ok=True)
    command = bindir / "anki-x"
    if command.exists() or command.is_symlink():
        owned = command.is_symlink() and command.resolve().name == "anki-x"
        text = command.read_text(errors="ignore")[:400] if not command.is_symlink() else ""
        if not owned and "# anki-x managed launcher" not in text:
            raise RuntimeError("命令位置已有其他程序：" + str(command))
        command.unlink()
    command.write_text("#!/bin/sh\n# anki-x managed launcher\nexec " + shlex.quote(str(root / "anki-x")) + ' "$@"\n')
    command.chmod(0o755)
    launchers = [str(command)]
    if system == "macos":
        desktop = Path(os.environ.get("ANKI_X_SHORTCUT_DIR", Path.home() / "Applications")) / "anki-x.command"
        desktop.parent.mkdir(parents=True, exist_ok=True)
        desktop.write_text("#!/bin/sh\nexec " + shlex.quote(str(root / "anki-x")) + "\n")
        desktop.chmod(0o755)
        launchers.append(str(desktop))
    else:
        desktop = Path(os.environ.get("ANKI_X_SHORTCUT_DIR", Path.home() / ".local/share/applications")) / "anki-x.desktop"
        desktop.parent.mkdir(parents=True, exist_ok=True)
        desktop.write_text('[Desktop Entry]\nType=Application\nName=anki-x\nComment=Learn with Anki in your terminal\nExec="' + str(root / "anki-x").replace('"', '\\"') + '"\nTerminal=true\nCategories=Education;\n')
        launchers.append(str(desktop))
    return launchers


def install_payload(payload, paths, version=__version__, *, lock_held=False):
    payload = Path(payload).resolve()
    executable = "anki-x.exe" if os.name == "nt" else "anki-x"
    if not (payload / executable).is_file():
        raise RuntimeError("发行包中缺少可执行文件。")
    if not all(c.isalnum() or c in ".-_" for c in version):
        raise RuntimeError("无效版本号。")
    paths.ensure()
    with (nullcontext() if lock_held else SessionLock(paths.state)):
        previous = installation(paths)
        releases = paths.data / "runtime"
        releases.mkdir(parents=True, exist_ok=True)
        target = releases / version
        if not target.exists():
            stage = Path(tempfile.mkdtemp(prefix=".install-", dir=releases))
            try:
                shutil.copytree(payload, stage, dirs_exist_ok=True)
                if os.name != "nt":
                    (stage / executable).chmod(0o755)
                result = subprocess.run([str(stage / executable), "--version"], capture_output=True, text=True, timeout=30)
                if result.returncode or result.stdout.strip() != version:
                    raise RuntimeError("新版本启动验证失败，已保留旧版本。")
                stage.rename(target)
            finally:
                if stage.exists():
                    shutil.rmtree(stage)
        result = subprocess.run([str(target / executable), "--version"], capture_output=True, text=True, encoding="utf-8", timeout=30)
        if result.returncode or result.stdout.strip() != version:
            raise RuntimeError("安装目录验证失败，未切换程序入口。")
        launchers = _launcher(paths, target)
        write_json(paths.data / "installation.json", {"version": version, "root": str(target),
                   "previous": previous.get("root") if previous.get("root") != str(target) else previous.get("previous"),
                   "launchers": launchers})
        return target


def check_update():
    request = urllib.request.Request(f"https://api.github.com/repos/{REPOSITORY}/releases/latest",
                                     headers={"Accept": "application/vnd.github+json", "User-Agent": "anki-x"})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            release = json.load(response)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return {"available": False, "message": "暂无可公开下载的稳定版本。内测更新请使用仓库提供的安装包。"}
        raise RuntimeError("暂时无法检查更新，请稍后重试。") from exc
    version = release["tag_name"].removeprefix("v")
    available = Version(version) > Version(__version__)
    return {"available": available, "version": version, "assets": release.get("assets", []),
            "message": "发现新版本 " + version if available else "当前已是最新版本。"}


def apply_update(paths, release=None, *, lock_held=False):
    release = release or check_update()
    if not release.get("available"):
        return release["message"]
    system, cpu = system_id()
    filename = f"anki-x-{release['version']}-{system}-{cpu}.zip"
    assets = {item["name"]: item for item in release["assets"]}
    if filename not in assets or "SHA256SUMS" not in assets:
        raise RuntimeError("此版本还没有当前平台的完整更新包。")
    with urllib.request.urlopen(assets["SHA256SUMS"]["browser_download_url"], timeout=15) as response:
        checksums = response.read(1024 * 1024).decode("utf-8")
    digest = next((line.split()[0] for line in checksums.splitlines() if len(line.split()) == 2 and line.split()[1].lstrip("*") == filename), None)
    if digest is None:
        raise RuntimeError("更新包缺少校验值。")
    package = download_verified(assets[filename]["browser_download_url"], digest, paths.cache / "updates" / filename)
    with tempfile.TemporaryDirectory(prefix="anki-x-update-", dir=paths.cache) as folder:
        extract_zip(package, folder)
        root = Path(folder) / "anki-x"
        install_payload(root, paths, release["version"], lock_held=lock_held)
    return "更新已安装，下次启动使用新版本。可以运行 anki-x rollback 回退。"


def rollback(paths):
    with SessionLock(paths.state):
        installed = installation(paths)
        previous = Path(installed.get("previous", ""))
        if not installed.get("previous") or not previous.is_dir():
            raise RuntimeError("没有可回退的已安装版本。")
        executable = previous / ("anki-x.exe" if os.name == "nt" else "anki-x")
        result = subprocess.run([str(executable), "--version"], capture_output=True, text=True, timeout=30, check=True)
        launchers = _launcher(paths, previous)
        write_json(paths.data / "installation.json", {"version": result.stdout.strip(), "root": str(previous),
                   "previous": installed["root"], "launchers": launchers})
    return "已切换回上一个版本，下次启动生效。"


def uninstall(paths):
    with SessionLock(paths.state):
        installed = installation(paths)
        if not installed:
            raise RuntimeError("当前不是由 anki-x 安装器管理的安装，请使用原安装方式卸载。")
        for name in installed.get("launchers", []):
            path = Path(name)
            if path.is_file() or path.is_symlink():
                path.unlink()
        # A Windows process cannot delete its running executable. Leave the
        # version cache for the installer cleanup step, without deleting data.
        if os.name != "nt":
            shutil.rmtree(paths.data / "runtime", ignore_errors=True)
        (paths.data / "installation.json").unlink(missing_ok=True)
    return "程序入口已卸载，设置、恢复记录和 Anki 词库已保留。"


def run_update_command(args, paths):
    if args.command == "update":
        print(apply_update(paths))
    elif args.command == "rollback":
        print(rollback(paths))
    else:
        if not args.yes and input("卸载 anki-x 程序，保留词库和设置？输入 y 确认：").lower() != "y":
            return 0
        print(uninstall(paths))
    return 0
