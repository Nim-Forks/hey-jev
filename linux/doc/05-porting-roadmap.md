# Port status (Linux) — done ledger + open items

## Done

- Full brain parity with the Windows port (backends, skills, memory,
  timers/alarms, persistence, cost tracking, gate override)
- Decision backends: KEV > Typesafe > OpenRouter-Jev
  (`typesafe/jev-1.13`, `JEV_MODEL`), KEV-aware gate (0.45/0.65,
  `JEV_GATE`) — identical to the Windows port
- Linux action layer: pactl volume/mute, playerctl media, gsettings dark
  mode (GNOME), loginctl lock, systemctl suspend, desktop-id app launches,
  pkill quits
- `machine_context()` Linux-native (/proc, df, power_supply, pgrep)
- `chime()` freedesktop sound via paplay, terminal-bell fallback
- `pick_input()` skips PipeWire monitors, prefers mic devices
- **Languages (STT)**: `WHISPER_LANGUAGES` env (install.sh language prompt)
  → `whisper_spec()` switches to the multilingual `small` model when
  non-English languages are configured and it is cached; Whisper
  auto-detects per turn; English-only fallback otherwise. install.sh
  downloads both models (small.en + multilingual small)
- systemd system unit (`hey-jev.service`) with `Restart=always` and
  `XDG_RUNTIME_DIR` so PipeWire is reachable from a system service
- `install.sh` interactive setup (apt deps, venv, mic default source,
  interactive `.env` prompts — existing values as defaults, all optional
  vars may be empty — service name prompt, deploy-service integration,
  cloudflared detection + ingress/DNS-route automation with printed
  instructions when it can't)
- `deploy-service.sh` generates the systemd unit for the **current user**
  (no hardcoded usernames anywhere in the repo)
- `--remote` web server identical to Windows (pure Python): token gate,
  quota, per-user keys/memory/ntfy, tiles, location weather, history,
  cancel, timer alerts on all channels

## Open

1. **Dark mode / app-open** need a desktop session on the box; headless →
   `unsupported` lines (by design). A GNOME session on the attached display
   would light these up.
2. **playerctl** must be installed (install.sh does it) and a MPRIS player
   running for media keys.
3. **Default source** resets if hardware changes — re-run the pactl line
   from install.sh or re-run the script.
4. **Packaging** — none needed; systemd service is the ship state.
5. **Wake word** — could use openWakeWord/Porcupine in the systemd service
   later (mic is present, unlike the Windows box).
