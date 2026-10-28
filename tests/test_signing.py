import base64
import os
import subprocess
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from tools import signing


def mac_secrets():
    return {"MACOS_CERTIFICATE_BASE64": base64.b64encode(b"certificate-fixture").decode(),
            "MACOS_CERTIFICATE_PASSWORD": "do-not-log-this", "MACOS_SIGN_IDENTITY": "Developer ID Application: fixture",
            "APPLE_API_KEY_BASE64": base64.b64encode(b"key-fixture").decode(),
            "APPLE_API_KEY_ID": "key-id", "APPLE_API_ISSUER": "issuer"}


def test_no_secrets_never_claims_signing():
    with patch.dict(os.environ, {}, clear=True):
        assert not signing.configured("darwin")
        assert not signing.configured("win32")
        assert not signing.configured("linux")


def test_partial_and_required_signing_fail_without_falling_back():
    with patch.dict(os.environ, {"MACOS_SIGN_IDENTITY": "fixture"}, clear=True):
        with pytest.raises(signing.SigningError, match="partially"):
            signing.configured("darwin")
    with patch.dict(os.environ, {"ANKI_X_REQUIRE_SIGNING": "1"}, clear=True), patch.object(signing.sys, "platform", "darwin"):
        with pytest.raises(signing.SigningError, match="missing"):
            signing.prepare()


def test_command_errors_do_not_expose_password_or_tool_output():
    with patch.object(signing.subprocess, "run", return_value=Mock(returncode=1, stderr="do-not-log-this", stdout="")):
        with pytest.raises(signing.SigningError) as error:
            signing.checked(["signtool", "/p", "do-not-log-this"], "Sign")
    assert "do-not-log-this" not in str(error.value)


def test_only_accepted_notarization_may_be_stapled(tmp_path):
    with patch.dict(os.environ, mac_secrets(), clear=True), patch.object(signing, "checked", return_value='{"status":"Invalid"}') as checked:
        with pytest.raises(signing.SigningError, match="not accepted"):
            signing.notarize(tmp_path / "test.dmg", staple=True)
        assert checked.call_count == 1
    with patch.dict(os.environ, mac_secrets(), clear=True), patch.object(signing, "checked", side_effect=['{"status":"Accepted"}', "", ""]) as checked:
        assert signing.notarize(tmp_path / "test.dmg", staple=True)
        assert "staple" in checked.call_args_list[1].args[0]
        assert "validate" in checked.call_args_list[2].args[0]


def test_temporary_certificate_is_removed_and_original_keychains_restored(tmp_path):
    values = dict(mac_secrets(), RUNNER_TEMP=str(tmp_path))
    calls = []

    def execute(command, label, **kwargs):
        calls.append(command)
        if command == ["security", "list-keychains", "-d", "user"]:
            return '"/original/login.keychain-db"\n'
        if command[:2] == ["security", "create-keychain"]:
            Path(command[-1]).write_bytes(b"temporary")
        return ""

    with patch.dict(os.environ, values, clear=True), patch.object(signing.sys, "platform", "darwin"), patch.object(signing, "checked", side_effect=execute):
        signing.prepare()
        directory = signing.signing_directory()
        assert not (directory / "certificate.p12").exists()
        assert (directory / "notary.p8").read_bytes() == b"key-fixture"
        signing.cleanup()
        assert not directory.exists()
    assert ["security", "list-keychains", "-d", "user", "-s", "/original/login.keychain-db"] in calls
