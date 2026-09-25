# Troubleshooting (WSL Ubuntu)

## `paplay` plays nothing / "connection refused"

WSLg PulseAudio socket gone: `wsl --update`, then `wsl --shutdown`, reopen.
Confirm `echo $PULSE_SERVER` → `unix:/mnt/wslg/PulseServer`, `pactl info`
prints a server.

## Mic records silence / no sources

1. `pactl list sources short` — want an RDP source, not just monitors.
2. Windows mic privacy on.
3. `wsl --update`; restart WSL after Windows mic changes.
4. Bare test: `parecord`/`paplay` outside the app.

## sounddevice: "Invalid sample rate", device unavailable, or only `null`

PortAudio is on raw ALSA, not the WSLg server. Recreate `/etc/asound.conf`
([02-install.md](02-install.md)), confirm `libasound2-plugins` installed.

## `import sounddevice` → PortAudio not found

`sudo apt install libportaudio2` (Linux wheels don't bundle it).

## pip install fails on pyobjc

Expected. Two-step install or the `sys_platform` marker
([02-install.md](02-install.md)).

## `need TYPESAFE_API_KEY and FISH_AUDIO_API_KEY ...`

`.env` in the repo root, exact name, values without quotes, app started from
the repo root. Empty key + no `security` CLI raises `FileNotFoundError` —
that means the value was blank.

## afplay / FileNotFoundError on playback

You're running the **original repo code**; the port's `play_wav` fixes this.
Or install the paplay shim: `~/bin/afplay` → `exec paplay "$1"`.

## PTT misses keys when a Windows window has focus

Wayland limitation — XWayland grabs only see X11-window keystrokes. Use
`--wake`.

## pynput import error / DISPLAY not set

Confirm `echo $DISPLAY` → `:0`; start from a WSLg terminal or export
`DISPLAY=:0`.

## Everything is slow / venv weirdness

Cloned into `/mnt/c`. Re-clone into `~/code`.

## Jev/Fish/OpenRouter requests hang or 401

- DNS: `ping api.typesafe.ai`.
- Proxy/VPN on Windows can block WSL traffic.
- 401 = key wrong in `.env` (trailing spaces, quotes).

## She keeps saying "sorry, say that again"

Same as Windows — check `> heard:` transcript first, then confidences vs
the gate. KEV note: [../jev-compatible.md](../jev-compatible.md) §2.
