# Troubleshooting (Debian 13)

## `pactl` fails / no sound

- PipeWire user session must be up: `systemctl --user status pipewire
  pipewire-pulse` (both active on this box).
- A **system** service reaches PipeWire only with
  `XDG_RUNTIME_DIR=/run/user/1000` — the shipped unit sets it.

## Mic records the wrong thing (music/loopback)

The default source was the monitor. `install.sh` fixes it; verify:

```bash
pactl get-default-source    # should be alsa_input.…, not …monitor
pactl set-default-source alsa_input.pci-0000_75_00.6.analog-stereo
```

## sounddevice: "No libportaudio" / device errors

`sudo apt install libportaudio2 pipewire-alsa` — then ALSA `default` routes
into PipeWire.

## Media keys do nothing

`sudo apt install playerctl`, and a MPRIS player must be running:
`playerctl -l` (expect e.g. `spotify`, `firefox`). Spotify Linux exposes
MPRIS; a browser playing YouTube exposes `chromium`.

## Dark mode / app open: "unsupported"

No GNOME/X11 session on a headless box — by design. Run a desktop session
on the attached display, or wire a different desktop's settings backend.

## systemctl suspend fails

Polkit may require an active local session for suspend from a service.
Test manually first: `systemctl suspend` in your SSH session; if it fails,
add a polkit rule or map sleep to lock instead.

## Service flaps / dies on start

`journalctl -u hey-jev -n 50` — usual suspects: missing venv (re-run
install.sh), missing `.env` keys (startup gate messages), port 8765 already
bound (another instance running).

## Port 8765 already in use

`ss -tlnp | grep 8765` — kill the stray process or change `REMOTE_PORT`.

## Tunnel page unreachable

1. `systemctl status cloudflared-<zone>` — running?
2. `grep -A2 heylinux ~/.cloudflared/config.yml` — ingress line present?
3. `cloudflared tunnel route dns <tunnel-id> heylinux.your-domain.tld` — DNS route created?
4. `journalctl -u cloudflared-<zone> -f` while opening the page.

## Whisper slow

CPU int8 `small.en` ≈ 1-2 s per utterance on this box — fine. `base.en` if
you want faster; `large-v3` if you add RAM/GPU.

## Console shows escape garbage

`journalctl` output is UTF-8; set `PYTHONUTF8=1` in the unit if needed.
