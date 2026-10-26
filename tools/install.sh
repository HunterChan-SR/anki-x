#!/bin/sh
set -eu
project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
bin_dir=${ANKI_X_BIN_DIR:-"$HOME/.local/bin"}
target="$bin_dir/anki-x"
mkdir -p "$bin_dir"
if [ -e "$target" ] || [ -L "$target" ]; then
    if [ "$(readlink "$target" 2>/dev/null || true)" != "$project_dir/bin/anki-x" ]; then
        printf '%s\n' "Refusing to replace existing command: $target" >&2
        exit 1
    fi
else
    ln -s "$project_dir/bin/anki-x" "$target"
fi
chmod +x "$project_dir/bin/anki-x"
printf 'Installed: %s\n' "$target"
"$target" --version
