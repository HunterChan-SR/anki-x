import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from anki_x.storage import Settings, read_json, write_json
from anki_x.updater import install_payload, rollback, uninstall
from test_productization import paths_at


@unittest.skipIf(os.name == "nt", "real Windows launchers are verified by frozen installation CI")
class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.paths = paths_at(self.root / "user")
        self.paths.ensure()
        frozen = patch("sys.frozen", True, create=True)
        frozen.start()
        self.addCleanup(frozen.stop)
        self.environment = patch.dict(os.environ, {"ANKI_X_BIN_DIR": str(self.root / "bin"),
                                                    "ANKI_X_SHORTCUT_DIR": str(self.root / "shortcuts"), "ANKI_X_NO_PATH_UPDATE": "1"})
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def payload(self, version, fail=False):
        root = self.root / ("payload-" + version)
        root.mkdir()
        executable = root / "anki-x"
        executable.write_text("#!/bin/sh\n" + ("exit 1\n" if fail else "printf '%s\\n' '" + version + "'\n"))
        executable.chmod(0o755)
        return root

    def test_upgrade_and_rollback_keep_user_state(self):
        settings = Settings(self.paths)
        settings.set("autoplay", False)
        pending = {"state": "sending", "method": "scheduling.answer"}
        write_json(self.paths.state / "pending.json", pending)
        first = install_payload(self.payload("1.0.0"), self.paths, "1.0.0")
        second = install_payload(self.payload("1.1.0"), self.paths, "1.1.0")
        self.assertEqual(read_json(self.paths.data / "installation.json")["previous"], str(first))
        rollback(self.paths)
        current = read_json(self.paths.data / "installation.json")
        self.assertEqual(current["root"], str(first))
        self.assertEqual(current["previous"], str(second))
        self.assertFalse(Settings(self.paths).get("autoplay"))
        self.assertEqual(read_json(self.paths.state / "pending.json"), pending)

    def test_failed_new_build_keeps_old_launcher(self):
        first = install_payload(self.payload("1.0.0"), self.paths, "1.0.0")
        before = (self.root / "bin/anki-x").read_text()
        with self.assertRaises(RuntimeError):
            install_payload(self.payload("2.0.0", fail=True), self.paths, "2.0.0")
        self.assertEqual((self.root / "bin/anki-x").read_text(), before)
        self.assertEqual(read_json(self.paths.data / "installation.json")["root"], str(first))

    def test_uninstall_removes_program_only(self):
        install_payload(self.payload("1.0.0"), self.paths, "1.0.0")
        Settings(self.paths).set("show_title", False)
        uninstall(self.paths)
        self.assertFalse((self.root / "bin/anki-x").exists())
        self.assertTrue((self.paths.state / "preferences.json").exists())
        self.assertFalse(Settings(self.paths).get("show_title"))


if __name__ == "__main__":
    unittest.main()
