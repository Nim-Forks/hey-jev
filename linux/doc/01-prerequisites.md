# Prerequisites (Debian 13)

## System packages (install.sh does all of this)

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip libportaudio2 playerctl \
    pipewire-alsa libasound2-plugins
```

- `libportaudio2` — sounddevice Linux wheels don't bundle PortAudio
- `playerctl` — MPRIS media control (play/pause/next/previous)
- `pipewire-alsa` — routes ALSA `default` into PipeWire so PortAudio sees
  the right devices
- `python3-venv` — venv module

## Python 3.13

Debian 13 ships Python 3.13 — exactly what the port targets. `python3
--version` to confirm.

## Audio stack (PipeWire)

the machine runs PipeWire + pipewire-pulse. Volume/mute go through `pactl`
(`@DEFAULT_SINK@`), so no direct PipeWire API calls are needed.

**Important**: the default *source* on this box was the monitor (loopback),
not the mic. `install.sh` runs:

```bash
pactl set-default-source alsa_input.pci-0000_75_00.6.analog-stereo
```

(adjust the name if hardware changes — `pactl list short sources`). The
port's `pick_input()` also skips anything with "monitor" in its name.

## Desktop session (for app control + PTT)

This box is headless-ish (no GNOME session). Consequences:

- **dark mode / app open / PTT** need an X11/GNOME session; without one they
  fail gracefully ("unsupported") — the **web remote** is the primary
  interface
- media keys via `playerctl` work headless (MPRIS over the session bus) as
  long as a media player runs in the user session

## Cloudflared (already present)

`cloudflared` is installed system-wide and a tunnel
(`cloudflared-<zone>.service`) is **already running** with a wildcard
for `*.your-domain.tld` → local NPM (docker :80). The install adds an explicit
ingress for the web remote (see [02-install.md](02-install.md)).

## Tailscale (already present)

`100.76.159.62` (the machine) — SSH and the web remote are reachable
away-from-home over Tailscale without any tunnel.
