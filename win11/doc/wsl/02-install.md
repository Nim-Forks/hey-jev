# Install (WSL2 Ubuntu)

## 1. Clone INSIDE the WSL filesystem

```bash
mkdir -p ~/code && cd ~/code
git clone https://github.com/henryklunaris/hey-jev.git
cd hey-jev
```

`/mnt/c` is a 9P share — pip and venvs are ~10x slower there and flaky.

## 2. Create the venv

```bash
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
```

## 3. Install the dependencies

`requirements.txt` lists `pyobjc-framework-Cocoa>=11.0` — fails to build on
Linux. Two options:

### Option A — everything except pyobjc (works today)

```bash
.venv/bin/pip install requests "python-dotenv>=1.0" "numpy>=2.0" \
    "sounddevice>=0.5" "soundfile>=0.13" "pynput>=1.8" "faster-whisper>=1.2"
```

### Option B — fix the repo properly

```
pyobjc-framework-Cocoa>=11.0; sys_platform == "darwin"
```

then `.venv/bin/pip install -r requirements.txt` works everywhere.

## 4. Bridge ALSA to the WSLg PulseAudio server

```bash
sudo tee /etc/asound.conf > /dev/null <<'EOF'
pcm.!default {
    type pulse
    fallback "sysdefault"
    hint { show on description "PulseAudio (WSLg)" }
}
ctl.!default {
    type pulse
}
EOF
```

Verify: `.venv/bin/python -c "import sounddevice as sd; print(sd.query_devices())"`
should show WSLg/RDP sink and source entries, not just `null`.

## 5. Keys

`.env` in the repo root, mandatory on WSL (`chmod 600 .env`) — see
[03-api-keys.md](03-api-keys.md).

## 6. Whisper model

First run downloads `small.en` (~250 MB) into `~/.cache/huggingface`.
