# anki-x

Learn English with Anki Desktop from your terminal, using Anki's own scheduling,
decks and synchronization. Includes deck navigation, pronunciation, autoplay,
undo and session restoration.

```sh
npm install -g anki-x@next
anki-x
```

Requires Node.js 22.14+. The first launch downloads the exact native runtime
from the project's GitHub Release and verifies a SHA-256 pinned in this npm
package. Later launches work offline. No Python installation or npm lifecycle
scripts are needed. Supports macOS 13+ (Apple Silicon/Intel), Windows 10/11 x64,
and Linux x64 with glibc 2.35+. Anki Desktop and its connector are configured
through the first-run setup. Current releases are unsigned prereleases.

Upgrade with `npm install -g anki-x@next`; uninstall with `npm uninstall -g anki-x`.
Both preserve your Anki collection and preferences. Downloaded runtimes remain
in your user cache (`~/Library/Caches/anki-x/npm`, `%LOCALAPPDATA%/anki-x/npm`,
or `$XDG_CACHE_HOME/anki-x/npm`, defaulting to `~/.cache/anki-x/npm` on Linux).
`ANKI_X_NPM_CACHE` overrides this cache location. Old runtime caches can be deleted
after closing anki-x; they contain no learning data.

[Documentation and source](https://github.com/HunterChan-SR/anki-x).
Original code: MIT. The runtime includes separately licensed dependencies and
the official AnkiConnect add-on; corresponding notices and source accompany it.
The npm launcher uses fflate (MIT).
