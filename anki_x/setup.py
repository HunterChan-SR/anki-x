"""Verified Anki download and reversible local add-on setup."""

from __future__ import annotations

import json
import os
import secrets
import shutil
import socket
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from .bootstrap import ADDON_ID, ASSETS, addon_config, anki_is_running, port_available
from .downloads import download_verified, extract_tar_zst, extract_zip, sha256
from .platforms import find_anki, system_id
from .storage import read_json, write_json


def install_addon(base, paths, settings, *, repair_port=False):
    if anki_is_running():
        raise RuntimeError("请先从 Anki 菜单正常退出 Anki，再点击安装/修复。现有学习记录会由 Anki 保存。")
    base = Path(base).expanduser()
    target = base / "addons21" / ADDON_ID
    manifest = read_json(ASSETS / "ankiconnect.json")
    package = ASSETS / "ankiconnect.ankiaddon"
    if sha256(package) != manifest["sha256"]:
        raise RuntimeError("随包插件校验失败，请重新安装 anki-x。")
    prior = addon_config(base)
    old_config, old_meta = prior if prior else ({}, {})
    config = dict(old_config)
    port = int(config.get("webBindPort", 8765))
    if not prior or repair_port:
        if not port_available(port):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
        config["webBindPort"] = port
    if not prior:
        config["webBindAddress"] = "127.0.0.1"
        config["apiKey"] = secrets.token_urlsafe(32)
    target.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".anki-x-addon-", dir=target.parent))
    backup = paths.data / "addon-backups" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f") / ADDON_ID
    replaced = False
    try:
        extract_zip(package, stage)
        if target.exists():
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(target, backup)
            if (target / "user_files").is_dir():
                shutil.copytree(target / "user_files", stage / "user_files")
        meta = dict(old_meta)
        meta.update({"name": "Anki-Connect", "disabled": False, "config": config})
        write_json(stage / "meta.json", meta)
        if target.exists():
            shutil.rmtree(target)
        stage.rename(target)
        replaced = True
        settings.set("anki_base", str(base))
        settings.set("url", f"http://127.0.0.1:{port}")
        write_json(paths.data / "addon-installation.json", {"source_commit": manifest["commit"], "sha256": manifest["sha256"],
                                                           "base": str(base), "backup": str(backup) if backup.exists() else None})
    except Exception:
        if replaced and target.exists():
            shutil.rmtree(target)
        if backup.exists() and not target.exists():
            shutil.copytree(backup, target)
        raise
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    return target


def anki_release():
    manifest = read_json(ASSETS / "anki-releases.json")
    system, cpu = system_id()
    item = manifest["releases"].get(system + "-" + cpu)
    if item is None:
        raise RuntimeError("当前系统/CPU 暂无已验证的 Anki 安装包，请从 Anki 官网安装。")
    return dict(item, version=manifest["version"], url=f"https://github.com/ankitects/anki/releases/download/{manifest['version']}/{item['file']}")


def install_anki(paths, settings, progress=None):
    release = anki_release()
    destination = paths.cache / "downloads" / release["file"]
    download_verified(release["url"], release["sha256"], destination, progress)
    system, _ = system_id()
    if system == "macos":
        mount = Path(tempfile.mkdtemp(prefix="anki-x-dmg-"))
        try:
            subprocess.run(["hdiutil", "attach", str(destination), "-nobrowse", "-readonly", "-mountpoint", str(mount)],
                           check=True, capture_output=True, timeout=120)
            source = mount / "Anki.app"
            if not source.is_dir():
                raise RuntimeError("Anki 安装镜像缺少应用。")
            target = Path.home() / "Applications/Anki.app"
            if target.exists():
                raise RuntimeError("用户应用目录已有 Anki，请先选择现有安装。")
            target.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(["ditto", str(source), str(target)], check=True, capture_output=True, timeout=180)
        finally:
            subprocess.run(["hdiutil", "detach", str(mount)], capture_output=True, timeout=30)
            shutil.rmtree(mount, ignore_errors=True)
        executable = target
    elif system == "windows":
        # Display the vendor installer; elevation and installation location stay
        # under the user's normal Windows installer interaction.
        result = subprocess.run(["msiexec.exe", "/i", str(destination), "/passive", "/norestart"], timeout=900)
        if result.returncode not in (0, 3010):
            raise RuntimeError(f"Anki 安装未完成（代码 {result.returncode}），可重新运行安装。")
        executable = find_anki(data_dir=paths.data)
        if executable is None:
            raise RuntimeError("Anki 安装后暂未找到，请在高级设置中选择安装位置。")
    else:
        target = paths.data / "dependencies"
        target.mkdir(parents=True, exist_ok=True)
        stage = Path(tempfile.mkdtemp(prefix="anki-extract-", dir=paths.cache))
        try:
            extract_tar_zst(destination, stage)
            source = next((p for p in stage.iterdir() if p.is_dir() and (p / "anki").exists()), None)
            if source is None:
                raise RuntimeError("Anki 压缩包中未找到启动程序。")
            installed = target / source.name
            if installed.exists():
                executable = installed / "anki"
            else:
                shutil.move(str(source), installed)
                executable = installed / "anki"
        finally:
            shutil.rmtree(stage, ignore_errors=True)
    settings.set("anki_executable", str(executable))
    return executable
