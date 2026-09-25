# Prerequisites (Windows 11)

## Python 3.13+

Install from [python.org/downloads](https://www.python.org/downloads/).
Tick **"Add python.exe to PATH"** in the installer, or just use the `py`
launcher which the installer registers automatically.

Check:

```powershell
py -3 --version
```

3.13 is known-good (verified: all port dependencies resolve as Windows
wheels). 3.14 works too.

> If `python` opens the Microsoft Store instead, that is the Store execution
> alias, not a real Python. Disable it under
> **Settings > Apps > Advanced app settings > App execution aliases**, or just
> always use `py -3`. See [06-troubleshooting.md](06-troubleshooting.md).

## Git (optional)

Only needed to clone the repo. [git-scm.com](https://git-scm.com/download/win).

## Spotify desktop app

Required for the music commands. Get it from
[spotify.com/download](https://www.spotify.com/download) — the desktop app,
not the web player. Media keys reach the active global media session;
Spotify in-app volume maps to system volume on Windows.

## Microphone (desktop modes only)

Any working default microphone + **Settings > Privacy & Security >
Microphone > desktop apps** on. The port auto-picks a mic when Windows has
no default input and offers `--list-devices`/`--device`. If the machine has
**no mic endpoint at all** (this PC: only "Remote Audio", output-only),
desktop `--wake`/PTT can't run — use the web remote from a phone
([04-running.md](04-running.md)).

## API keys

- **Fish Audio** — required, always (TTS playback)
- Decision backend — one of: `KEV_URL` + `KEV_API_KEY` (priority 1),
  `TYPESAFE_API_KEY` (2), `OPENROUTER_API_KEY` (3, also powers LLM answers)
- Optional: `LLM_MODEL`, `NTFY_URL` (phone push), `REMOTE_*` (web server)

Details: [03-api-keys.md](03-api-keys.md).

## Optional infrastructure on this PC (for the web remote)

- **cloudflared** — Cloudflare Tunnel: trusted HTTPS, away-from-home reach
- **Nginx Proxy Manager** (80/81) — LAN reverse proxy, DNS-01 Let's Encrypt,
  Websockets Support toggle
- **Coolify** — container front alternative (audio/USB stay host-side)
- `restart-remote.ps1` — kill + restart + health-check in one command

Selection via `REMOTE_FRONT` in `.env`; the server always binds plain HTTP.
Only needed for the web remote, not for the desktop app.

## Not needed on Windows

- py2app / the app bundle — macOS packaging
- the Keychain — replaced by Credential Manager + `.env`
- Accessibility permissions — macOS concept; pynput needs nothing special
- the afplay shim — obsolete; the port plays audio through sounddevice
