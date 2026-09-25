# Prerequisites (WSL2 Ubuntu)

## WSL2 + WSLg

From Windows PowerShell:

```powershell
wsl --status          # Default Version should be 2
wsl --update          # refresh WSLg, mic/audio fixes land here
wsl -d Ubuntu-26.04   # or your distro
```

WSLg provides XWayland (`DISPLAY=:0`), PulseAudio
(`PULSE_SERVER=unix:/mnt/wslg/PulseServer`), and RDP audio sink/source
(`/mnt/wslg/PulseAudioRDPSink`, `PulseAudioRDPSource`).

## Ubuntu packages

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip git \
    libportaudio2 pulseaudio-utils libasound2-plugins
```

- `libportaudio2` — sounddevice Linux wheels don't bundle PortAudio.
- `pulseaudio-utils` — `pactl`, `paplay`, `parecord` (tests + playback).
- `libasound2-plugins` — ALSA→PulseAudio bridge for the asound.conf.

## Verify audio out and mic **before** running the app

```bash
paplay /usr/share/sounds/alsa/Front_Center.wav
parecord --channels=1 --rate=16000 test.wav   # speak, Ctrl+C
paplay test.wav
```

Windows side: allow mic access (**Settings > Privacy & Security >
Microphone > desktop apps**).

## Windows interop (for controlling the host later)

```bash
powershell.exe -NoProfile -Command "'interop works'"
```

Config in `/etc/wsl.conf` (`[interop] enabled=true`).

## API keys

Mandatory `.env` — the macOS `security` CLI doesn't exist in Ubuntu and the
original repo's `secrets_store.py` would raise `FileNotFoundError`
([03-api-keys.md](03-api-keys.md)).

## Not needed

- py2app / the app bundle — macOS packaging
- Keychain — replaced by `.env`
- A GUI desktop inside WSL — WSLg provides windows itself
