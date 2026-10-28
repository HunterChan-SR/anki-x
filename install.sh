#!/bin/sh
# anki-x release installer. No Python or developer tools required.
set -eu
anki_x_version=${ANKI_X_VERSION:-1.0.0rc2}
anki_x_base="https://github.com/HunterChan-SR/anki-x/releases/download/v$anki_x_version"
case "$(uname -s)" in
  Darwin) anki_x_os=macos ;;
  Linux) anki_x_os=linux ;;
  *) printf '%s\n' 'Use install.ps1 on Windows.' >&2; exit 1 ;;
esac
case "$(uname -m)" in
  arm64|aarch64) anki_x_arch=arm64 ;;
  x86_64|amd64) anki_x_arch=x64 ;;
  *) printf '%s\n' 'This CPU architecture does not have a published installer.' >&2; exit 1 ;;
esac
command -v curl >/dev/null || { printf '%s\n' 'curl is required to download the release.' >&2; exit 1; }
command -v unzip >/dev/null || { printf '%s\n' 'unzip is required to extract the release.' >&2; exit 1; }
anki_x_tmp=$(mktemp -d)
trap 'rm -rf "$anki_x_tmp"' EXIT HUP INT TERM
anki_x_file="anki-x-$anki_x_version-$anki_x_os-$anki_x_arch.zip"
curl --fail --location --proto '=https' --tlsv1.2 "$anki_x_base/$anki_x_file" -o "$anki_x_tmp/$anki_x_file"
curl --fail --location --proto '=https' --tlsv1.2 "$anki_x_base/SHA256SUMS" -o "$anki_x_tmp/SHA256SUMS"
anki_x_expected=$(awk -v filename="$anki_x_file" '$2 == filename {print $1}' "$anki_x_tmp/SHA256SUMS")
if command -v sha256sum >/dev/null; then
  anki_x_actual=$(sha256sum "$anki_x_tmp/$anki_x_file" | awk '{print $1}')
else
  anki_x_actual=$(shasum -a 256 "$anki_x_tmp/$anki_x_file" | awk '{print $1}')
fi
if [ -z "$anki_x_expected" ] || [ "$anki_x_actual" != "$anki_x_expected" ]; then
  printf '%s\n' 'Download verification failed. Nothing was installed.' >&2
  exit 1
fi
unzip -q "$anki_x_tmp/$anki_x_file" -d "$anki_x_tmp/release"
"$anki_x_tmp/release/anki-x/anki-x" install
