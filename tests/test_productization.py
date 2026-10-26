import base64
import io
import json
import os
import tempfile
import unittest
import wave
import zipfile
from pathlib import Path
from unittest.mock import Mock, patch

from anki_x.api import AnkiError
from anki_x.bootstrap import CORE_METHODS, Connector, Environment, connection_candidates
from anki_x.downloads import DownloadError, extract_zip
from anki_x.setup import install_addon
from anki_x.storage import AppPaths, SessionLock, Settings, migrate_legacy, read_json, write_json


def paths_at(root):
    return AppPaths(root / "config", root / "data", root / "state", root / "cache", root / "logs")


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.paths = paths_at(self.root / "new")
        self.paths.ensure()

    def test_migration_preserves_preferences_navigation_and_uncertain_writes(self):
        legacy = self.root / "old"
        write_json(legacy / "config.json", {"url": "http://127.0.0.1:8766", "deck": "英语"})
        expected = {"preferences.json": {"autoplay": False, "show_title": False},
                    "navigation.json": {"version": 1, "profiles": {"test": {"view": "review"}}},
                    "pending.json": {"state": "sending", "method": "scheduling.answer", "params": {"cardId": "8"}}}
        for name, value in expected.items():
            write_json(legacy / ".state" / name, value)
        report = migrate_legacy(self.paths, legacy)
        for name, value in expected.items():
            self.assertEqual(read_json(self.paths.state / name), value)
            self.assertEqual(read_json(legacy / ".state" / name), value)
            self.assertEqual(read_json(Path(report["backup"]) / name), value)
        Settings(self.paths).set("autoplay", True)
        migrate_legacy(self.paths, legacy)
        self.assertTrue(Settings(self.paths).get("autoplay"))

    def test_two_process_locks_cannot_write_at_once(self):
        with SessionLock(self.paths.state):
            with self.assertRaises(RuntimeError):
                with SessionLock(self.paths.state):
                    pass
        with SessionLock(self.paths.state):
            pass

    def test_corrupt_user_config_is_backed_up_and_does_not_prevent_start(self):
        self.paths.config_file.write_text("{bad")
        settings = Settings(self.paths)
        self.assertTrue(settings.get("autoplay"))
        self.assertEqual(len(settings.warnings), 1)
        self.assertEqual(len(list(self.paths.config.glob("*.invalid-*"))), 1)

    def test_migration_does_not_overwrite_new_user_config(self):
        legacy = self.root / "old"
        write_json(legacy / "config.json", {"deck": "old"})
        write_json(self.paths.config_file, {"deck": "new"})
        migrate_legacy(self.paths, legacy)
        self.assertEqual(Settings(self.paths).get("deck"), "new")


class SetupTests(StorageTests):
    def test_addon_repair_preserves_key_custom_settings_and_user_files(self):
        base = self.root / "Anki2"
        addon = base / "addons21/2055492159"
        write_json(addon / "config.json", {"webBindPort": 8765, "apiKey": None})
        write_json(addon / "meta.json", {"config": {"webBindPort": 9888, "apiKey": "private-key", "custom": "keep"},
                                        "update_enabled": False, "mod": 123, "disabled": True})
        (addon / "user_files").mkdir()
        (addon / "user_files/personal.txt").write_text("preserve")
        with patch("anki_x.setup.anki_is_running", return_value=False), patch("anki_x.setup.port_available", return_value=True):
            install_addon(base, self.paths, Settings(self.paths), repair_port=True)
        meta = read_json(addon / "meta.json")
        self.assertEqual(meta["config"]["apiKey"], "private-key")
        self.assertEqual(meta["config"]["webBindPort"], 9888)
        self.assertEqual(meta["config"]["custom"], "keep")
        self.assertEqual(meta["mod"], 123)
        self.assertFalse(meta["update_enabled"])
        self.assertFalse(meta["disabled"])
        self.assertEqual((addon / "user_files/personal.txt").read_text(), "preserve")

    def test_running_anki_blocks_disk_plugin_replacement(self):
        with patch("anki_x.setup.anki_is_running", return_value=True):
            with self.assertRaisesRegex(RuntimeError, "退出"):
                install_addon(self.root / "Anki2", self.paths, Settings(self.paths))

    def test_new_addon_uses_loopback_and_own_key(self):
        base = self.root / "Anki2"
        with patch("anki_x.setup.anki_is_running", return_value=False), patch("anki_x.setup.port_available", return_value=True):
            install_addon(base, self.paths, Settings(self.paths))
        meta = read_json(base / "addons21/2055492159/meta.json")
        self.assertEqual(meta["config"]["webBindAddress"], "127.0.0.1")
        self.assertGreater(len(meta["config"]["apiKey"]), 20)

    def test_zip_traversal_is_rejected(self):
        package = self.root / "bad.zip"
        with zipfile.ZipFile(package, "w") as archive:
            archive.writestr("../escape", "bad")
        with self.assertRaises(DownloadError):
            extract_zip(package, self.root / "out")
        self.assertFalse((self.root / "escape").exists())

    def test_detects_custom_addon_port_without_leaking_key_to_remote_url(self):
        base = self.root / "Anki2"
        write_json(base / "addons21/2055492159/config.json", {"webBindPort": 9765, "apiKey": "local-secret"})
        settings = Settings(self.paths)
        settings.set("anki_base", str(base))
        with patch("anki_x.bootstrap.anki_bases", return_value=[base]), patch.dict(os.environ, {}, clear=True):
            candidates, _ = connection_candidates(settings, self.paths)
            self.assertEqual(candidates[0].url, "http://127.0.0.1:9765")
            self.assertEqual(candidates[0].key, "local-secret")
            remote, _ = connection_candidates(settings, self.paths, "https://example.com")
            self.assertIsNone(remote[0].key)


class AudioTests(unittest.TestCase):
    def test_bundled_decoder_and_null_output_complete(self):
        from anki_x.audio import play
        with tempfile.TemporaryDirectory() as tmp:
            sound = Path(tmp) / "test.wav"
            with wave.open(str(sound), "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(16000)
                wav.writeframes(b"\0\0" * 1600)
            with patch.dict(os.environ, {"ANKI_X_AUDIO_BACKEND": "null"}):
                player = play(sound)
                self.assertEqual(player.wait(timeout=5), 0)


if __name__ == "__main__":
    unittest.main()
