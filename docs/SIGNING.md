# Publisher signing and notarization

The public `1.0.0rc1` packages are unsigned prereleases. This guide prepares later signed builds; it is not a claim that a signed build has run.

Use **Repository Settings → Secrets and variables → Actions**. Do not paste keys or passwords into issues, chat messages or source files. GitHub currently contains no signing secrets for this project.

## macOS Developer ID and Apple notarization

Configure all six repository Secrets together:

| Secret | Value supplied by the publisher |
| --- | --- |
| `MACOS_CERTIFICATE_BASE64` | Base64 of the Developer ID Application `.p12` export, including its private key |
| `MACOS_CERTIFICATE_PASSWORD` | Password protecting that `.p12` |
| `MACOS_SIGN_IDENTITY` | Exact Developer ID Application identity in the certificate |
| `APPLE_API_KEY_BASE64` | Base64 of the Apple notarization-capable API `.p8` key |
| `APPLE_API_KEY_ID` | Apple API key ID |
| `APPLE_API_ISSUER` | Apple API issuer ID |

The build creates an isolated temporary keychain, imports the certificate, signs the frozen runtime, submits ZIP/app/DMG to Apple's notary service, requires `Accepted`, and staples/validates tickets on the app and DMG. It restores the previous keychain search list and removes temporary credentials in an `always()` cleanup step. A real Developer ID identity and functioning Apple account are required.

## Windows Authenticode

For a signing provider that permits exporting a PFX, configure:

| Secret | Value supplied by the publisher |
| --- | --- |
| `WINDOWS_CERTIFICATE_BASE64` | Base64 of the code-signing PFX including its private key |
| `WINDOWS_CERTIFICATE_PASSWORD` | Password protecting the PFX |

The workflow signs executable/library payloads and the final setup.exe with SHA-256, requests a timestamp, then verifies Authenticode. If the publisher uses a hardware token or cloud signing provider instead of exportable PFX, adapt the provider-specific signing command before running; do not export keys that the provider prohibits exporting. No certificate or signing service is purchased automatically.

## Running and validating

Run **Actions → Build and verify anki-x → Run workflow**, select the productization branch, and enable **signed**. Ordinary pushes and pull requests do not receive signing credentials. Missing or partial secrets cause an explicitly requested signed build to fail, rather than silently emitting unsigned artifacts.

Each platform emits a signing report. Only a successful real signing/notarization run, verified signatures, and the resulting accepted artifacts count as completion. The included tests cover fail-closed configuration, secret-safe errors, accepted-status gating and cleanup; they cannot validate the publisher's identity or replace a real signed build.

After downloading a signed build, verify macOS Gatekeeper installation from a quarantined download and Windows publisher identity on a normal user account. Keep existing unsigned releases labeled as such; publish newly signed bytes under a new release version instead of replacing published checksums.

Primary references:

- https://docs.github.com/en/actions/how-tos/deploy/deploy-to-third-party-platforms/sign-xcode-applications
- https://pyinstaller.org/en/stable/feature-notes.html#macos-binary-code-signing
- https://learn.microsoft.com/en-us/windows/win32/seccrypto/signtool
