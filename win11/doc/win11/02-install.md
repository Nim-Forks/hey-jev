# Install (Windows 11)

## 1. Clone

```powershell
git clone https://github.com/henryklunaris/hey-jev.git
cd hey-jev\win11
```

## 2. Create the venv and install

### Path A — the port (recommended)

The port has its own `requirements.txt` (no pyobjc, plus pystray/Pillow for
the tray icon):

```powershell
py -3 -m venv .venv
.venv\Scripts\pip.exe install -r requirements.txt
```

Verified: all dependencies resolve as Windows wheels on Python 3.13.

### Path B — the original Mac repo's code, on Windows

If you want to run the repo-root `siri.py` directly, its `requirements.txt`
still lists `pyobjc-framework-Cocoa>=11.0` (line 8), which **cannot build on
Windows**. Install the rest explicitly:

```powershell
cd ..        # repo root
py -3 -m venv .venv
.venv\Scripts\pip.exe install requests "python-dotenv>=1.0" "numpy>=2.0" `
    "sounddevice>=0.5" "soundfile>=0.13" "pynput>=1.8" "faster-whisper>=1.2"
```

(The long-term fix for path B is the `sys_platform == "darwin"` marker on
line 8 — the port sidesteps it entirely.)

## 3. Keys

Create `.env` from the template before first run:

```powershell
Copy-Item .env.example .env   # then fill in your keys
```

`.env` values win over Windows Credential Manager (the port's Keys… panel
writes there via `keyring`). Full variable reference:
[03-api-keys.md](03-api-keys.md).

If PowerShell blocks `Activate.ps1` (execution policy), either
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` or skip activation —
every command in these docs calls `.venv\Scripts\python.exe` directly.

## 4. Whisper model

On first real run, faster-whisper downloads the `small.en` model (~250 MB)
into `%USERPROFILE%\.cache\huggingface`. One time, then it is offline and free.

## 5. Handy script

`restart-remote.ps1` — kills any running `--remote` server, starts a fresh
one, health-checks it, prints the PID and log:

```powershell
powershell -ExecutionPolicy Bypass -File restart-remote.ps1
```
