# Install (Debian 13)

## 1. Clone

```bash
mkdir -p ~/code && cd ~/code
git clone https://github.com/Nim-Forks/hey-jev.git
cd hey-jev/linux
```

(Clone inside the Linux filesystem; local development on Windows lives in
`win11/` — `linux/` is deployed to the machine.)

## 2. One-command install

```bash
bash install.sh          # apt packages + venv + default mic + service
bash deploy-service.sh   # generates hey-jev.service for the current user and starts it
```

`install.sh` is idempotent and does:

1. `sudo apt install` the packages from [01-prerequisites.md](01-prerequisites.md)
2. `python3 -m venv .venv` + `pip install -r requirements.txt`
3. sets the default PulseAudio **source** to the mic (skips monitors)

`deploy-service.sh` then:

1. generates `hey-jev.service` with the **current user**, home and venv paths
   filled in (no hardcoded usernames in the repo)
2. installs it as a system service (`siri.py --remote` as your user,
   `Restart=always`, `XDG_RUNTIME_DIR=/run/user/<uid>` so PipeWire is
   reachable)
3. `systemctl enable --now hey-jev` + health-check `http://127.0.0.1:8765/health`

## 3. Keys

```bash
cp .env.example .env   # then fill in
chmod 600 .env
```

Same variable names as the Windows port — you can literally copy
`win11/.env` (same backends, LLM, token, ntfy). Reference:
[03-api-keys.md](03-api-keys.md).

## 4. Whisper model + languages

`install.sh` pre-downloads `small.en` (~250 MB, English-only) into
`~/.cache/huggingface`.

It then asks for **extra languages** (comma-separated codes, e.g. `en,hr,de`;
empty = English only). Any non-English entry downloads the **multilingual
`small` model** (~470 MB — one model covers ~99 languages) and writes
`WHISPER_LANGUAGES=en,…` into `.env`. With it, STT **auto-detects** the
spoken language and she answers in it. Skip the prompt to stay English-only.

## 5. Restart / logs

```bash
systemctl restart hey-jev          # or bash restart-remote.sh
journalctl -u hey-jev -f           # live trace
systemctl status hey-jev
```
