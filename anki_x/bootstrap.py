"""Discover and connect to local Anki without user-edited ports or JSON."""

from __future__ import annotations

import json
import os
import socket
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path

from packaging.version import InvalidVersion, Version

from .api import AnkiError, Client, ConnectionError
from .platforms import anki_bases, find_anki, launch_anki
from .storage import read_json


ASSETS = Path(__file__).parent / "assets"
ADDON_ID = "2055492159"
CORE_METHODS = {"collection.get", "decks.list", "decks.get", "decks.getCounts", "cards.get", "cards.search",
                "cards.render", "notes.get", "scheduling.getQueue", "scheduling.predict", "scheduling.answer",
                "collection.undo", "operations.get", "application.navigate", "statistics.getToday", "media.get"}


@dataclass
class Candidate:
    url: str
    key: str | None = field(default=None, repr=False)
    base: Path | None = None


@dataclass
class Environment:
    state: str
    title: str
    message: str
    executable: Path | None = None
    base: Path | None = None
    endpoint: str | None = None
    profile: str | None = None
    anki_version: str | None = None
    tested_version: bool = False
    missing_methods: list = field(default_factory=list)
    client: Client | None = field(default=None, repr=False)

    def diagnostic(self):
        return {"state": self.state, "title": self.title, "endpoint": self.endpoint,
                "anki_version": self.anki_version, "tested_version": self.tested_version,
                "missing_methods": self.missing_methods, "anki_found": self.executable is not None,
                "addon_found": bool(self.base and (self.base / "addons21" / ADDON_ID).exists())}


def addon_config(base):
    directory = Path(base) / "addons21" / ADDON_ID
    if not directory.exists():
        return None
    defaults = read_json(directory / "config.json")
    meta = read_json(directory / "meta.json")
    defaults.update(meta.get("config", {}))
    return defaults, meta


def connection_candidates(settings, paths, explicit_url=None):
    local = []
    bases = anki_bases(settings.get("anki_base"))
    for base in bases:
        try:
            config = addon_config(base)
            if config:
                config, _ = config
                port = int(config.get("webBindPort", 8765))
                if not 1 <= port <= 65535:
                    continue
                key = config.get("apiKey")
                local.append(Candidate(f"http://127.0.0.1:{port}", key if isinstance(key, str) else None, base))
        except (OSError, ValueError, TypeError):
            continue
    ordered = []
    for url in (explicit_url, os.environ.get("ANKI_CONNECT_URL"), settings.get("url")):
        if not url:
            continue
        parsed = urllib.parse.urlsplit(url)
        # A local add-on credential must never be attached to a remote URL.
        match = next((item for item in local if item.url.rstrip("/") == url.removesuffix("/api/v1").rstrip("/")), None)
        key = os.environ.get("ANKI_API_KEY") or (match.key if match else None)
        if parsed.scheme in ("http", "https") and parsed.hostname and not parsed.username and not parsed.password:
            ordered.append(Candidate(url, key, match.base if match else None))
    if not explicit_url and not os.environ.get("ANKI_CONNECT_URL"):
        ordered += local
        ordered.append(Candidate("http://127.0.0.1:8765", os.environ.get("ANKI_API_KEY")))
    result, seen = [], set()
    for candidate in ordered:
        canonical = candidate.url.removesuffix("/api/v1").rstrip("/")
        if canonical not in seen:
            result.append(candidate)
            seen.add(canonical)
    return result, bases


def anki_is_running():
    import psutil
    for process in psutil.process_iter(["name", "exe", "cmdline"]):
        try:
            name = (process.info["name"] or "").lower()
            executable = process.info["exe"] or ""
            command = process.info["cmdline"] or []
            if name in ("anki", "anki.exe") or "/Anki.app/" in executable:
                return True
            if len(command) > 2 and command[1:3] == ["-m", "aqt"]:
                return True
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            continue
    return False


def port_available(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


class Connector:
    def __init__(self, paths, settings, explicit_url=None):
        self.paths, self.settings, self.explicit_url = paths, settings, explicit_url
        self.environment = None

    def inspect(self):
        executable = find_anki(self.settings.get("anki_executable"), self.paths.data)
        candidates, bases = connection_candidates(self.settings, self.paths, self.explicit_url)
        base = next((p for p in bases if (p / "addons21" / ADDON_ID).exists()), bases[0])
        compatibility = None
        authentication = False
        for candidate in candidates:
            client = Client(candidate.url, key=candidate.key, timeout=2, journal=self.paths.state / "pending.json")
            try:
                description = client.call("api.describe")
                if not isinstance(description, dict) or description.get("apiMajor") != 1:
                    continue
                available = {item["name"] for item in description.get("methods", []) if item.get("available")}
                missing = sorted(CORE_METHODS - available)
                version = description.get("ankiVersion", "unknown")
                try:
                    supported = Version(version) >= Version("26.8")
                    tested = Version(version) in {Version("26.8"), Version("26.9.3")}
                except InvalidVersion:
                    supported, tested = False, False
                if missing or not supported:
                    compatibility = Environment("incompatible", "Anki 接入需要更新", "当前 Anki 或插件缺少学习所需能力，请使用兼容版本。",
                                                executable, candidate.base or base, client.endpoint, anki_version=version,
                                                missing_methods=missing)
                    continue
                try:
                    collection = client.connect()
                except AnkiError:
                    client.timeout = 15
                    compatibility = Environment("profile_needed", "请先打开一个 Anki 账户", "在 Anki 中完成首次设置或选择账户，然后点击重新检查。",
                                                executable, candidate.base or base, client.endpoint, anki_version=version, client=client)
                    continue
                self.settings.set("url", candidate.url.removesuffix("/api/v1"))
                if candidate.base:
                    self.settings.set("anki_base", str(candidate.base))
                self.environment = Environment("ready", "Anki 已连接", "可以开始学习。", executable, candidate.base or base,
                                               client.endpoint, collection["profile"], version, tested, client=client)
                client.timeout = 15
                return self.environment
            except ConnectionError as exc:
                authentication |= exc.code in (401, 403)
            except AnkiError as exc:
                authentication |= isinstance(exc.data, dict) and exc.data.get("type") == "authenticationRequired"
        if compatibility:
            result = compatibility
        elif authentication:
            result = Environment("authentication", "需要检查连接权限", "请确认选择了正确的 Anki 数据目录；现有插件密钥会保留。", executable, base)
        elif executable is None:
            result = Environment("anki_missing", "先安装 Anki", "anki-x 使用 Anki 保存词库和安排复习。可以直接下载官方兼容版本。", None, base)
        else:
            try:
                config = addon_config(base)
            except (ValueError, OSError, TypeError):
                config = None
            if config is None:
                result = Environment("plugin_missing", "完成 Anki 接入", "安装随包提供的官方连接插件，之后即可自动连接。", executable, base)
            elif config[1].get("disabled"):
                result = Environment("plugin_disabled", "连接插件已被停用", "可以启用连接插件，然后重新打开 Anki。", executable, base)
            elif not anki_is_running():
                result = Environment("anki_stopped", "正在等待 Anki", "点击启动 Anki，加载账户后会自动连接。", executable, base)
            else:
                port = int(config[0].get("webBindPort", 8765))
                conflict = not port_available(port)
                result = Environment("port_conflict" if conflict else "restart_needed", "连接尚未就绪",
                                     "请正常退出 Anki 后修复连接，再由 anki-x 重新启动。" if conflict
                                     else "插件安装或更新后需要重启 Anki；也请完成 Anki 窗口中的提示。", executable, base)
        self.environment = result
        return result

    def start_anki(self):
        report = self.environment or self.inspect()
        if report.executable is None:
            raise RuntimeError("尚未找到 Anki，请先安装。")
        return launch_anki(report.executable, self.settings.get("anki_base"))
