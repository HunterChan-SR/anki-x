"""Versioned, atomic user storage independent of the installation directory."""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from platformdirs import PlatformDirs
import portalocker


DEFAULT_CONFIG = {"version": 1, "url": None, "deck": None, "anki_base": None,
                  "anki_executable": None, "autoplay": True, "show_title": True}


def read_json(path: Path, default=None):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else (default or {})
    except FileNotFoundError:
        return default or {}


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix="." + path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        if os.name != "nt":
            os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


@dataclass(frozen=True)
class AppPaths:
    config: Path
    data: Path
    state: Path
    cache: Path
    logs: Path

    @classmethod
    def discover(cls):
        home = os.environ.get("ANKI_X_HOME")
        if home:
            root = Path(home).expanduser().resolve()
            paths = cls(root / "config", root / "data", root / "state", root / "cache", root / "logs")
        else:
            dirs = PlatformDirs("anki-x", appauthor=False)
            paths = cls(Path(dirs.user_config_dir), Path(dirs.user_data_dir),
                        Path(dirs.user_state_dir) / "state", Path(dirs.user_cache_dir), Path(dirs.user_log_dir))
        if os.environ.get("ANKI_X_STATE_DIR"):
            paths = cls(paths.config, paths.data, Path(os.environ["ANKI_X_STATE_DIR"]).expanduser(), paths.cache, paths.logs)
        return paths

    @property
    def config_file(self):
        return self.config / "config.json"

    def ensure(self):
        for path in {self.config, self.data, self.state, self.cache, self.logs}:
            path.mkdir(parents=True, exist_ok=True)


class Settings:
    def __init__(self, paths: AppPaths):
        self.paths = paths
        self.warnings = []
        self.values = dict(DEFAULT_CONFIG)
        self.values.update(self._load(paths.config_file))
        self.preferences = self._load(paths.state / "preferences.json")
        for key in ("autoplay", "show_title"):
            if not isinstance(self.values.get(key), bool):
                self.values[key] = DEFAULT_CONFIG[key]
            if key in self.preferences and not isinstance(self.preferences[key], bool):
                self.preferences.pop(key)

    def _load(self, path):
        try:
            return read_json(path)
        except (ValueError, UnicodeError):
            suffix = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
            backup = path.with_name(path.name + ".invalid-" + suffix)
            shutil.copy2(path, backup)
            self.warnings.append("配置格式有误，已备份并使用默认设置：" + str(backup))
            return {}

    def get(self, key, default=None):
        return self.preferences.get(key, self.values.get(key, default))

    def set(self, key, value):
        if key in ("autoplay", "show_title"):
            updated = dict(self.preferences, **{key: bool(value)})
            write_json(self.paths.state / "preferences.json", updated)
            self.preferences = updated
        else:
            updated = dict(self.values, **{key: value})
            write_json(self.paths.config_file, updated)
            self.values = updated


class SessionLock:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.lock = None

    def __enter__(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        self.lock = portalocker.Lock(str(self.directory / "session.lock"), mode="a+", timeout=0)
        try:
            stream = self.lock.acquire()
        except portalocker.exceptions.LockException as exc:
            raise RuntimeError("另一个 anki-x 正在运行，请先退出它。") from exc
        stream.seek(0)
        stream.truncate()
        json.dump({"pid": os.getpid()}, stream)
        stream.flush()
        return self

    def __exit__(self, *args):
        if self.lock:
            self.lock.release()


def legacy_candidates():
    candidates = []
    if os.environ.get("ANKI_X_LEGACY_HOME"):
        candidates.append(Path(os.environ["ANKI_X_LEGACY_HOME"]).expanduser())
    if not getattr(sys, "frozen", False):
        candidates.append(Path(__file__).resolve().parents[1])
    command = shutil.which("anki-x")
    if command:
        candidates.append(Path(command).resolve().parents[1])
    candidates.append(Path.cwd())
    return list(dict.fromkeys(p for p in candidates if (p / "anki_x").is_dir()
                              and ((p / ".state").is_dir() or (p / "config.json").is_file())))


def migrate_legacy(paths: AppPaths, root: Path | None = None):
    """Copy, back up and mark a migration. Never overwrite newer user files."""
    paths.ensure()
    marker = paths.data / "migration-v1.json"
    if marker.exists():
        return read_json(marker)
    roots = [Path(root)] if root else legacy_candidates()
    source = next((p for p in roots if p.is_dir()), None)
    if source is None:
        return {"migrated": False}
    source_state = source / ".state"
    # A live old client could update its journal during copying. The same
    # native file lock used by the old Unix client also works with portalocker.
    with SessionLock(source_state):
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
        backup = paths.data / "migration-backup" / stamp
        mapping = [(source / "config.json", paths.config_file)]
        mapping += [(source_state / name, paths.state / name)
                    for name in ("preferences.json", "navigation.json", "pending.json")]
        copied = []
        for old, new in mapping:
            if not old.is_file() or old.resolve() == new.resolve():
                continue
            backup.mkdir(parents=True, exist_ok=True)
            shutil.copy2(old, backup / old.name)
            if new.exists():
                continue
            # Preserve pending records verbatim, including unknown outcomes.
            if old.name == "config.json":
                old_config = read_json(old)
                value = {key: old_config[key] for key in DEFAULT_CONFIG if key in old_config}
                value["version"] = 1
                write_json(new, value)
            else:
                value = read_json(old)
                write_json(new, value)
            copied.append(old.name)
        result = {"version": 1, "migrated": bool(copied), "source": str(source),
                  "backup": str(backup) if backup.exists() else None, "files": copied}
        write_json(marker, result)
        return result
