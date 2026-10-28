anki-x is a cross-platform terminal companion for Anki Desktop. This release candidate adds PyPI, npm and Homebrew distribution and automatic publishing from version tags. Existing study, onboarding and recovery features are retained.

Package-manager installs keep updates and uninstalls under the original package manager. The npm launcher downloads a SHA-256-pinned native runtime on first launch and then works from its local cache. PyPI requires Python 3.12+; npm requires Node 22.14+; Homebrew uses the self-contained binaries.

Download the matching platform package. No Python installation is required.

- macOS Apple Silicon / Intel: DMG application or ZIP installer.
- Windows x64: setup.exe or ZIP installer.
- Linux x64: ZIP plus install.sh; glibc 2.35+ and Anki's desktop libraries are required.

Use `SHA256SUMS` to verify downloaded assets. Third-party licenses and the corresponding AnkiConnect source are included.

This is a prerelease. Signing/notarization is not claimed unless explicitly listed with the uploaded release. Automated platform checks cover the application, native Anki scheduler, isolated first-run setup, and source-independent installation. Hosted CI is not a substitute for a user testing operating-system security prompts and physical audio on each platform.

Existing 0.2.x users: exit the old client before installation. Configuration and navigation are backed up and migrated to standard user directories. Anki learning data stays in Anki. Run `anki-x paths` to inspect locations, and `anki-x rollback` to return to a previously installed packaged version.
