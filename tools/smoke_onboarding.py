#!/usr/bin/env python3
"""Actual Anki process + bundled add-on + first-run cards in a disposable profile."""
import json
import os
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def server(base, ready):
    # Set before importing aqt: never attach to a personal Anki instance.
    os.environ["ANKI_SINGLE_INSTANCE_KEY"] = "anki-x-onboarding-" + uuid.uuid4().hex
    from anki.lang import set_lang
    from aqt.profiles import ProfileManager
    set_lang("en")
    pm = ProfileManager(Path(base))
    pm.setupMeta()
    pm.profiles()
    pm.load(pm.profiles()[0])
    pm.meta["firstRun"] = False
    pm.meta["defaultLang"] = "en"
    pm.set_update_check(False)
    pm.set_check_for_addon_updates(False)
    pm.profile["autoSync"] = False
    pm.profile["numBackups"] = 0
    pm.save()
    profile = pm.name
    pm.db.close()
    import aqt
    from aqt.qt import QTimer
    app = aqt._run(["anki", "-b", base, "-p", profile, "-l", "en"], exec=False)
    timer = QTimer()

    def report_ready():
        if aqt.mw.col is not None and aqt.mw.state == "deckBrowser":
            Path(ready).write_text("ready")
            timer.stop()

    timer.timeout.connect(report_ready)
    timer.start(100)
    QTimer.singleShot(120000, lambda: app.exit(1))
    app.exec()


def main():
    os.environ.setdefault("ANKI_X_AUDIO_BACKEND", "null")
    from anki_x.bootstrap import Connector
    from anki_x.content import starter_deck
    from anki_x.review import Reviewer
    from anki_x.setup import install_addon
    from anki_x.storage import AppPaths, Settings
    with tempfile.TemporaryDirectory(prefix="anki-x-onboarding-") as folder:
        root = Path(folder)
        paths = AppPaths(root / "config", root / "data", root / "state", root / "cache", root / "logs")
        paths.ensure()
        settings = Settings(paths)
        base = root / "Anki2"
        # Only the running-process guard is bypassed for this uniquely identified
        # disposable Anki instance. The installer and all API work are real.
        with patch("anki_x.setup.anki_is_running", return_value=False):
            install_addon(base, paths, settings)
        ready = root / "ready"
        env = dict(os.environ, QT_QPA_PLATFORM="offscreen", QTWEBENGINE_CHROMIUM_FLAGS="--no-sandbox", ANKI_X_AUDIO_BACKEND="null")
        with (root / "server.log").open("w") as log:
            process = subprocess.Popen([sys.executable, __file__, "--server", str(base), str(ready)], env=env, stdout=log, stderr=log)
            client = None
            review = None
            try:
                deadline = time.monotonic() + 50
                while not ready.exists():
                    if process.poll() is not None or time.monotonic() >= deadline:
                        raise RuntimeError((root / "server.log").read_text()[-7000:])
                    time.sleep(0.1)
                report = Connector(paths, settings).inspect()
                assert report.state == "ready", report
                client = report.client
                name = starter_deck(client)
                assert client.deck_counts({"name": name})["total"] == 6
                starter_deck(client)
                assert client.deck_counts({"name": name})["total"] == 6
                review = Reviewer(client, name)
                review.start()
                card_id = review.state["card"]["id"]
                review.audio()
                assert review.player.wait(5) == 0
                review.reveal()
                result = review.grade("again")
                assert result["cardId"] == card_id
                records = client.col("reviews.list", cardIds=[card_id])["items"]
                assert len(records) == 1
                review.undo()
                assert client.col("reviews.list", cardIds=[card_id])["items"] == []
                print(json.dumps({"bundled_addon_installed": True, "local_key_discovered": True,
                                  "starter_cards": 6, "idempotent_import": True, "audio": True,
                                  "native_review_and_undo": True}, indent=2))
            finally:
                try:
                    if review:
                        review.close()
                finally:
                    if client:
                        try:
                            client.call("application.exit")
                        except Exception:
                            pass
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--server":
        server(sys.argv[2], sys.argv[3])
    else:
        main()
