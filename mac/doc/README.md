# Hey Jev on macOS

Status: **port exists, untested** — no Mac available for verification.
The platform layer (`mac/siri.py`) was copied from the original root
`siri.py` (which was tested on macOS Sequoia/Tahoe) and rewired to use
`shared/brain.py` + `shared/config.py` + `shared/remote_server.py`.

## Files

| File | Purpose |
| --- | --- |
| `siri.py` | macOS platform layer: osascript actions, afplay playback, Recorder, run_voice_assistant, main |
| `remote.py` | thin wrapper → shared/remote_server |
| `assistant_ui.py` | AppKit status window (copy from root, macOS-only) |
| `app.py` | entry point for the app bundle |
| `secrets_store.py` | **not needed** — shared/secrets_store.py is used; the Keychain is NOT used in the shared version (`.env` only) |
| `setup.py` | py2app packaging (copy from root) |
| `requirements.txt` | macOS deps incl. pyobjc |
| `.env.example` | same variables as win11/linux |

## Key differences from win11/linux

- **Secrets**: the shared `secrets_store.py` uses `.env` only (no Keychain).
  If you want Keychain support on macOS, extend
  `shared/secrets_store.py` with a platform-specific `get_secret` fallback.
- **ACTIONS**: osascript AppleScript commands (volume, Spotify, dark mode,
  lock, sleep) — copied from the root original.
- **Playback**: `afplay` via `config.play_wav_hook`.
- **Chime**: `/System/Library/Sounds/Glass.aiff` via `afplay`.
- **UI**: `assistant_ui.py` is the AppKit window (copied from root); the
  web remote page is identical (shared/web/).

## Setup (on a Mac)

```bash
git clone https://github.com/Nim-Forks/hey-jev.git
cd hey-jev
cd mac
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env        # fill in your keys
.venv/bin/python siri.py --text "hello there"
```

For the app bundle:
```bash
.venv/bin/python setup.py py2app -A
open "dist/Hey Jev - Fish Audio.app"
```

## Needs verification on a Mac

- `--text` mode (Jev decision + Fish TTS + afplay playback)
- `--wake` / `--remote` (mic recording, web remote serving)
- `assistant_ui.py` (AppKit window — copied from root, imports may need
  `sys.path` fix for `shared/`)
- `setup.py py2app` packaging (the shared/ directory must be bundled)

## Not tested / may need fixes

- `secrets_store.py` — the shared version doesn't use Keychain. If you want
  Keychain, add the original root's `keychain_value()`/`save_secret()`
  functions as platform overrides in `shared/config.py`.
- `assistant_ui.py` — imports `from secrets_store import ...` which needs
  the shared path fix (add `sys.path.insert` for the repo root).
