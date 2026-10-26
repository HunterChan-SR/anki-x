# Third-party components

anki-x's original application code is licensed under MIT. Third-party software retains its own copyright and license.

The distribution contains the official, unmodified AnkiConnect add-on at commit `62fc13d107c2b02130e503749e9933495c6456fb`, licensed GPL-3.0-or-later. Its corresponding complete source archive and full license are included in the release. AnkiConnect runs separately inside Anki Desktop and is accessed over its HTTP interface.

Runtime dependencies include Textual (MIT), Rich (MIT), platformdirs (MIT), portalocker (BSD-3-Clause), miniaudio and its bundled decoding backend (see miniaudio notices), CFFI (MIT), zstandard (BSD), psutil (BSD-3-Clause), and packaging (Apache-2.0 / BSD). The release's `licenses/` directory and `DEPENDENCIES.json` contain notices and exact build versions.

The six starter words, definitions, and example sentences are original anki-x material under MIT. Their demonstration audio was synthesized with Flite 2.2, voice `cmu_us_kal16`. See `licenses/Flite-COPYING.txt` for CMU and contributor notices. This small sample is for verifying the learning flow, not a bundled copy of any user's dictionary deck.

Anki Desktop is downloaded from the official `ankitects/anki` release, with the vendor's published SHA-256 verified before installation. It remains a separate application with its own license and account/data management.
