# Hey Jev on Linux (Debian, mini PC)

Status: **port built, deploy script ready** — `linux/` mirrors `win11/` with
a Linux-native action layer (pactl / playerctl / gsettings / loginctl /
systemd) and the same brain. The primary interface is the **web remote**
(`siri.py --remote` behind the machine's own cloudflared tunnel); desktop
PTT (`--wake`) works when a mic + X11 session are present.

## Files in this folder

1. [01-prerequisites.md](01-prerequisites.md) — Debian 13 packages, PipeWire notes
2. [02-install.md](02-install.md) — clone/venv, systemd service, default mic
3. [03-api-keys.md](03-api-keys.md) — same `.env` reference as Windows
4. [04-running.md](04-running.md) — modes, what she can do on Linux
5. [05-porting-roadmap.md](05-porting-roadmap.md) — done ledger + open items
6. [06-troubleshooting.md](06-troubleshooting.md)

## Feature matrix (current, Linux)

| Feature | State |
| --- | --- |
| Jev decisions — KEV > Typesafe > OpenRouter | works (same `.env` names as Windows) |
| LLM answers (`LLM_MODEL`, GLM 5.3 flash) | works, Jev-gated context (time / machine / memory) |
| Free-API skills: weather+rain, sunrise/sunset, currency, Wikipedia, jokes, news | works |
| Memory (web remote, per device) | works |
| Timers, reminders, daily alarms | works, persisted to `timers.json` |
| Phone push (ntfy) | works (`NTFY_URL` / per-device in Settings) |
| Web remote (`--remote`) + token gate + quota | works (pure Python, identical server) |
| Volume / mute (pactl, PipeWire) | works |
| Media play/pause/next/previous (playerctl, MPRIS) | works (Spotify Linux included) |
| Dark mode (gsettings, GNOME) | works only with a GNOME session; headless → `unsupported` |
| Lock / sleep (loginctl / systemctl suspend) | works, polkit permitting |
| App open/quit (desktop ids / pkill) | works for installed apps; missing apps → `unsupported` |
| Desktop PTT (`--wake`, right Alt) | works with X11 + mic; headless boxes use the web remote |
| Status window + tray | tkinter on X11; headless → not used |

## Hardware notes (this machine)

- Debian 13 (trixie), x86_64, Python 3.13.5, 12 GB RAM, 885 GB free
- **PipeWire** (pipewire + pipewire-pulse active) with a real mic
  (`alsa_input.…ALC269VC`) and speakers — `pactl` works
- Default **source** was the monitor (loopback) — `install.sh` sets the mic
  as default; `pick_input()` also skips monitors
- cloudflared already runs as a system service (`cloudflared-<zone>`)
  with `*.your-domain.tld` wildcard → local NPM (docker :80)
- Tailscale present (`100.76.159.62`) — away-from-home option
