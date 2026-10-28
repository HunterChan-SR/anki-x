import argparse
import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from anki_x import updater
from tools.prepare_channels import npm_version, prepare


@pytest.mark.parametrize("version,expected", [("1.0.0rc2", "1.0.0-rc.2"), ("1.2.3", "1.2.3"),
                                             ("2.0.0b4", "2.0.0-beta.4")])
def test_versions(version, expected):
    assert npm_version(version) == expected


def test_invalid_version():
    with pytest.raises(ValueError):
        npm_version("1.0.0/../../bad")


@pytest.mark.parametrize("manager", ["npm", "homebrew"])
def test_external_install_never_runs_native_update_or_uninstall(manager, tmp_path, capsys):
    with patch.dict(os.environ, {"ANKI_X_PACKAGE_MANAGER": manager}), patch.object(updater, "check_update") as network:
        for command in ("update", "rollback", "uninstall"):
            assert updater.run_update_command(argparse.Namespace(command=command), None) == 0
            assert manager in capsys.readouterr().out
        with pytest.raises(RuntimeError, match=manager):
            updater.install_payload(tmp_path, None)
        with pytest.raises(RuntimeError, match=manager):
            updater.apply_update(None, {"available": True})
        network.assert_not_called()


def test_source_install_does_not_modify_native_installation():
    with patch.dict(os.environ, {"ANKI_X_PACKAGE_MANAGER": ""}), patch("sys.frozen", False, create=True):
        assert updater.package_manager() in ("python", "uv", "pipx")
        assert updater.check_update()["available"] is False


def test_manifest_requires_all_platforms_and_pins_hashes(tmp_path):
    assets = tmp_path / "assets"
    assets.mkdir()
    with pytest.raises(FileNotFoundError):
        prepare(assets, tmp_path / "channels", version="1.0.0rc2")
    for platform in ("macos-arm64", "macos-x64", "windows-x64", "linux-x64"):
        (assets / f"anki-x-1.0.0rc2-{platform}.zip").write_bytes(platform.encode())
    manifest = prepare(assets, tmp_path / "channels", version="1.0.0rc2")
    assert len(manifest["platforms"]) == 4
    for item in manifest["platforms"].values():
        assert len(item["sha256"]) == 64
        assert "/v1.0.0rc2/" in item["url"]
    package = json.loads((tmp_path / "channels/npm/package.json").read_text())
    assert package["version"] == "1.0.0-rc.2"
    formula = (tmp_path / "channels/homebrew/Formula/anki-x.rb").read_text()
    assert 'ANKI_X_PACKAGE_MANAGER: "homebrew"' in formula
    assert 'version "1.0.0rc2"' in formula
