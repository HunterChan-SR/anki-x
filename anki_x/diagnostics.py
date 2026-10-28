"""User-exported diagnostics without credentials, note contents or profile names."""

import importlib.metadata
import json
import platform
from pathlib import Path

from . import __version__
from .platforms import system_id
from .storage import write_json


def export_diagnostics(paths, report=None):
    dependencies = {}
    for name in ("textual", "platformdirs", "portalocker", "miniaudio"):
        try:
            dependencies[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            dependencies[name] = "bundled"
    connection = report.diagnostic() if report else {}
    connection.pop("endpoint", None)
    value = {"anki_x_version": __version__, "platform": system_id(), "python": platform.python_version(),
             "dependencies": dependencies, "connection": connection,
             "pending_operation_present": (paths.state / "pending.json").exists()}
    destination = paths.logs / "diagnostics.json"
    write_json(destination, value)
    return destination
