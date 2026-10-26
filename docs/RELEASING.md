# Release process

1. Update `anki_x.__version__`, installer defaults, changelog and the compatibility record.
2. Run `uv sync --frozen`, the tests, native Anki onboarding smoke, and frozen package smoke.
3. Push the release branch. Every matrix job must pass; inspect its artifact and verification report.
4. Create a `v<version>` tag at the verified commit. The workflow rebuilds all targets, combines checksums and creates a **draft prerelease**.
5. Review download names, license/source bundle, installation on clean systems, upgrade/rollback, and release notes. Publish the reviewed release.

The macOS native packager accepts `MACOS_SIGN_IDENTITY` for a Developer ID identity already imported in the build keychain. Certificate import and Apple notarization require the project owner's signing credentials. Windows Authenticode similarly requires an available signing certificate and provider. Never put certificates, passwords, tokens, or private keys in the repository or release assets. Until configured, mark all packages as unsigned prereleases.

The build workflow currently covers macOS Apple Silicon, macOS Intel, Windows x64 and Linux x64. It does not claim ARM64 Windows/Linux support or every Linux distribution. The Anki upstream compatibility manifest is pinned to official version 26.09.3 and includes verified release checksums.

`uv.lock`, `requirements.lock` and `requirements-build.lock` record dependencies. Regenerate exports when changing dependencies; CI installs with hash checking. `tools/vendor_ankiconnect.py` only accepts the pinned, unmodified source checkout and bundles its corresponding source archive.

Release assets must include ZIPs, platform-native install entries where built, SHA256SUMS, install scripts and platform verification reports. The source archive is also automatically provided by GitHub for the tag.
