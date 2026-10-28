"""Optional publisher signing. Credentials come only from CI environment."""

from __future__ import annotations

import argparse
import base64
import json
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


class SigningError(RuntimeError):
    pass


def checked(command, label, *, timeout=120):
    """Do not log commands: some signing tools require password arguments."""
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        raise SigningError(label + " could not complete; check the signing runner.") from None
    if result.returncode:
        raise SigningError(label + " failed; signing secrets and provider access must be verified.")
    return result.stdout


def configured(system):
    if system == "darwin":
        names = ("MACOS_CERTIFICATE_BASE64", "MACOS_CERTIFICATE_PASSWORD", "MACOS_SIGN_IDENTITY",
                 "APPLE_API_KEY_BASE64", "APPLE_API_KEY_ID", "APPLE_API_ISSUER")
    elif system == "win32":
        names = ("WINDOWS_CERTIFICATE_BASE64", "WINDOWS_CERTIFICATE_PASSWORD")
    else:
        return False
    present = [bool(os.environ.get(name)) for name in names]
    if any(present) and not all(present):
        raise SigningError("Signing is partially configured; required secrets: " + ", ".join(names))
    return all(present)


def secure_file(path, encoded):
    try:
        content = base64.b64decode(encoded, validate=True)
    except ValueError:
        raise SigningError("A signing secret is not valid Base64.") from None
    path.write_bytes(content)
    if os.name != "nt":
        path.chmod(0o600)


def signing_directory():
    runner = Path(os.environ.get("RUNNER_TEMP", tempfile.gettempdir()))
    return runner / "anki-x-signing"


def prepare():
    if not configured(sys.platform):
        if os.environ.get("ANKI_X_REQUIRE_SIGNING"):
            raise SigningError("A signed build was requested but publisher signing secrets are missing.")
        print("Publisher signing is not configured; build remains an unsigned preview.")
        return
    directory = signing_directory()
    directory.mkdir(parents=True, exist_ok=True)
    if sys.platform == "darwin":
        keychain = directory / "build.keychain-db"
        certificate = directory / "certificate.p12"
        original = checked(["security", "list-keychains", "-d", "user"], "Read keychain search list")
        (directory / "original-keychains.json").write_text(json.dumps([line.strip().strip('"') for line in original.splitlines()]))
        password = secrets.token_urlsafe(32)
        checked(["security", "create-keychain", "-p", password, str(keychain)], "Create build keychain")
        checked(["security", "set-keychain-settings", "-lut", "21600", str(keychain)], "Configure build keychain")
        checked(["security", "unlock-keychain", "-p", password, str(keychain)], "Unlock build keychain")
        secure_file(certificate, os.environ["MACOS_CERTIFICATE_BASE64"])
        checked(["security", "import", str(certificate), "-P", os.environ["MACOS_CERTIFICATE_PASSWORD"],
                 "-t", "cert", "-f", "pkcs12", "-k", str(keychain), "-T", "/usr/bin/codesign"], "Import publisher certificate")
        checked(["security", "set-key-partition-list", "-S", "apple-tool:,apple:,codesign:", "-k", password, str(keychain)], "Authorize codesign")
        checked(["security", "list-keychains", "-d", "user", "-s", str(keychain),
                 *json.loads((directory / "original-keychains.json").read_text())], "Select build keychain")
        secure_file(directory / "notary.p8", os.environ["APPLE_API_KEY_BASE64"])
        certificate.unlink()
    else:
        secure_file(directory / "certificate.pfx", os.environ["WINDOWS_CERTIFICATE_BASE64"])
    print("Publisher signing credentials prepared in the temporary build directory.")


def cleanup():
    directory = signing_directory()
    if sys.platform == "darwin" and directory.exists():
        original = directory / "original-keychains.json"
        if original.exists():
            checked(["security", "list-keychains", "-d", "user", "-s", *json.loads(original.read_text())], "Restore keychains")
        keychain = directory / "build.keychain-db"
        if keychain.exists():
            checked(["security", "delete-keychain", str(keychain)], "Remove build keychain")
    if directory.exists():
        shutil.rmtree(directory)


def windows_tool():
    available = shutil.which("signtool")
    if available:
        return available
    sdk = Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)")) / "Windows Kits/10/bin"
    candidates = sorted(sdk.glob("*/x64/signtool.exe"), reverse=True)
    if not candidates:
        raise SigningError("Windows SDK SignTool is not installed.")
    return str(candidates[0])


def sign_windows(path):
    if not configured("win32"):
        return False
    tool = windows_tool()
    checked([tool, "sign", "/fd", "SHA256", "/td", "SHA256", "/tr", "http://timestamp.digicert.com",
             "/f", str(signing_directory() / "certificate.pfx"), "/p", os.environ["WINDOWS_CERTIFICATE_PASSWORD"],
             str(path)], "Sign Windows file")
    checked([tool, "verify", "/pa", "/all", str(path)], "Verify Windows signature")
    return True


def notarize(path, *, staple=False):
    if not configured("darwin"):
        return False
    reply = checked(["xcrun", "notarytool", "submit", str(path), "--key", str(signing_directory() / "notary.p8"),
                     "--key-id", os.environ["APPLE_API_KEY_ID"], "--issuer", os.environ["APPLE_API_ISSUER"],
                     "--wait", "--output-format", "json"], "Apple notarization", timeout=1200)
    if json.loads(reply).get("status") != "Accepted":
        raise SigningError("Apple notarization was not accepted.")
    if staple:
        checked(["xcrun", "stapler", "staple", str(path)], "Staple notarization ticket")
        checked(["xcrun", "stapler", "validate", str(path)], "Validate notarization ticket")
    return True


def notarize_app(path):
    if not configured("darwin"):
        return False
    archive = signing_directory() / "application.zip"
    checked(["ditto", "-c", "-k", "--keepParent", str(path), str(archive)], "Package app for notarization")
    notarize(archive)
    checked(["xcrun", "stapler", "staple", str(path)], "Staple application")
    checked(["codesign", "--verify", "--deep", "--strict", str(path)], "Verify application signature")
    archive.unlink(missing_ok=True)
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("prepare", "cleanup"))
    args = parser.parse_args()
    try:
        globals()[args.action]()
    except SigningError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
