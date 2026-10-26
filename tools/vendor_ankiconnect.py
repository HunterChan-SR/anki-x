#!/usr/bin/env python3
"""Build the pinned, unmodified official add-on plus corresponding source."""
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

COMMIT = "62fc13d107c2b02130e503749e9933495c6456fb"
root = Path(__file__).resolve().parents[1]
source = Path(sys.argv[1]).resolve()
head = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
if head != COMMIT:
    raise SystemExit("Unexpected AnkiConnect source commit")
if subprocess.check_output(["git", "-C", str(source), "diff", "--name-only", "HEAD"], text=True).strip():
    raise SystemExit("AnkiConnect source has changes")
subprocess.run([sys.executable, "tools/package_addon.py"], cwd=source, check=True)
assets = root / "anki_x/assets"
assets.mkdir(parents=True, exist_ok=True)
package = assets / "ankiconnect.ankiaddon"
archive = assets / "ankiconnect-source.tar.gz"
shutil.copy2(source / "AnkiConnect.zip", package)
subprocess.run(["git", "-C", str(source), "archive", "--format=tar.gz", "--prefix=ankiconnect/",
                "--output=" + str(archive), COMMIT], check=True)
(assets / "licenses").mkdir(exist_ok=True)
shutil.copy2(source / "LICENSE", assets / "licenses/AnkiConnect-NOTICE.txt")
manifest = {"commit": COMMIT, "package": "2055492159", "license": "GPL-3.0-or-later",
            "source": "https://git.sr.ht/~foosoft/anki-connect", "tested_anki": ["26.8", "26.9.3"],
            "sha256": hashlib.sha256(package.read_bytes()).hexdigest(),
            "source_sha256": hashlib.sha256(archive.read_bytes()).hexdigest()}
(assets / "ankiconnect.json").write_text(json.dumps(manifest, indent=2) + "\n")
print(json.dumps(manifest, indent=2))
