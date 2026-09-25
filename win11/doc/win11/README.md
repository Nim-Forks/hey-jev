# Hey Jev on Windows 11

Status: **implemented, web remote included.** The port lives in
[`../../../win11/`](../../../README.md): `siri.py` (brain + Windows actions),
`remote.py` (mic/PTT web server), `assistant_ui.py` (tkinter + tray),
`secrets_store.py` (Credential Manager + `.env`), `web/` (PTT page, settings,
tiles), `restart-remote.ps1` (one-command server restart).

## Files in this folder

1. [01-prerequisites.md](01-prerequisites.md) — Python 3.13+, py launcher, Spotify app
2. [02-install.md](02-install.md) — venv install (port vs original repo)
3. [03-api-keys.md](03-api-keys.md) — every `.env` variable: backends, LLM, remote, ntfy
4. [04-running.md](04-running.md) — `--text`, `--wake`, `--ui`, `--remote`, what she can do
5. [05-porting-roadmap.md](05-porting-roadmap.md) — done ledger + what's still open (ESP32)
6. [06-troubleshooting.md](06-troubleshooting.md)

## Feature matrix (current)

| Feature | State |
| --- | --- |
| Jev decisions — KEV > Typesafe > OpenRouter fallback | works |
| LLM answers (any OpenRouter model via `LLM_MODEL`) | works, Jev-gated context (time / machine status / memory) |
| Free-API skills: weather (+rain/snow verdicts), sunrise/sunset, currency, Wikipedia, jokes, news | works |
| Memory ("remember that…", recall, forget) | works, per-device browser localStorage |
| Timers, reminders, daily alarms | works, persisted to `timers.json`, missed reminders pushed on restart |
| Phone push (ntfy.sh) | works, opt-in via `NTFY_URL` / per-device in Settings |
| Web remote (`--remote`): phone/browser mic + PTT, typed text, cancel, tiles, replayable history, per-user keys in localStorage | works |
| HTTPS fronts: cloudflared / NPM / Coolify | works (this PC: NPM on 80/81 + tunnel) |
| Desktop app control (apps, volume, dark mode, lock/sleep, media keys) | works |
| Status window + tray (`--ui`) | works |
| Mic auto-pick when Windows has no default input | works |
| ESP32/Pico hardware actions | designed, not implemented ([../android/08-remote-mic-pc.md](../android/08-remote-mic-pc.md) §5) |

## Historical note

These docs originally covered running the **unported Mac repo** on Windows
(pyobjc build failure, afplay shim, two-step install). The port makes all of
that obsolete; [02-install.md](02-install.md) keeps both paths for reference.
