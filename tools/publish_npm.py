#!/usr/bin/env python3
"""Publish a packed npm artifact, safely resuming an already-uploaded version."""
import base64
import hashlib
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

folder = Path(sys.argv[1])
package = json.loads((folder / "package.json").read_text())
archives = list(folder.glob("*.tgz"))
assert len(archives) == 1, archives
archive = archives[0]
url = f"https://registry.npmjs.org/anki-x/{package['version']}"
try:
    with urllib.request.urlopen(url, timeout=30) as response:
        existing = json.load(response)
except urllib.error.HTTPError as exc:
    if exc.code != 404:
        raise
else:
    expected = "sha512-" + base64.b64encode(hashlib.sha512(archive.read_bytes()).digest()).decode()
    if existing["dist"].get("integrity") != expected:
        raise SystemExit("This npm version already exists with different content. Bump the version; do not overwrite it.")
    print("Identical npm version already published; nothing to upload.")
    raise SystemExit(0)
subprocess.run(["npm", "publish", str(archive), "--access", "public", "--tag", os.environ["NPM_DIST_TAG"],
                "--registry", "https://registry.npmjs.org/"], check=True)
