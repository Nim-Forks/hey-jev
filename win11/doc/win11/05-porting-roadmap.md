# Port status (Windows 11) — done ledger + open items

The port is implemented and running daily via the web remote. This doc
records what exists and what's left.

## Done

### 1. Platform layer
- `requirements.txt` without pyobjc (+ pystray/Pillow); root-repo path B
  still needs the two-step install ([02-install.md](02-install.md))
- Audio playback via sounddevice (`play_wav`); timer chime via `winsound`
- All 21 Mac actions ported natively (WASAPI volume, registry dark mode +
  broadcast, `rundll32` lock/sleep, URI schemes, `Stop-Process`, pynput
  media keys; `spotify_volume_*` maps to system volume)
- Mic auto-pick when Windows has no default input (`pick_input`)
- Secrets: Credential Manager (`keyring`) + `.env`-wins fallback
- UI: tkinter status window, tray icon (`assets/icon.png`), Keys panel,
  persisted mode, `--list-devices`/`--device`
- `restart-remote.ps1`: kill + restart + health-check in one command

### 2. Decision backends
- Three-tier priority: KEV (`KEV_URL`+`KEV_API_KEY`) → Typesafe → OpenRouter
  decisions API (`typesafe/jev-1.13`, `JEV_MODEL` override)
- KEV-aware confidence gate: 0.45 vs 0.65 (`JEV_GATE` override)
- Wire contract documented + smoke-tested: [../jev-compatible.md](../jev-compatible.md)

### 3. Skills (all free APIs, one `info_skill` fan-out question)
- Weather incl. "will it rain/snow" verdicts from hourly chances (wttr.in)
- Sunrise/sunset 24h local from wttr astronomy (no second API, no UTC bug)
- Currency (frankfurter.app), Wikipedia (summary + search fallback,
  authorship questions → LLM, personal-pronoun topics refused), jokes
  (icanhazdadjoke), news (BBC RSS world/tech)

### 4. Memory (per device, web remote)
- Facts in browser localStorage (cap 50), synced per connection
- Deterministic phrasing rules decide save/recall/forget (KEV noise-proof);
  recall rides the LLM context automatically; personal-pronoun topics never
  hit Wikipedia

### 5. LLM answers
- `LLM_MODEL` (currently `z-ai/glm-5.3-flash`) + `LLM_MAX_TOKENS` (300),
  `reasoning: {effort: "low"}` (GLM requires reasoning)
- Jev-gated context: `needs_time`, `needs_machine` (uptime/CPU/RAM/disk/
  battery/running apps, 60s cache) + memory facts
- Cost tracking per turn (Jev + LLM) → trace, web badge, `X-Cost` header —
  never spoken

### 6. Timers, alarms, push
- `timers.json` persistence (save on every mutation, reload at startup,
  missed reminders pushed once on restart)
- Daily alarms ("set an alarm for 7:30 am", "cancel my alarm"), self-
  rescheduling, shown in the timer list
- ntfy.sh phone push (`NTFY_URL` server default, per-device topic in
  Settings), opt-in; `ALERT_MESSAGE` default alert for unlabeled timers
- RLock fix for the save-while-locked deadlock

### 7. Web remote (`--remote`) — full feature set
- WebSocket turns + HTTP `POST /turn` (Termux/curl), `GET /health`
- PTT page: typed input box (top), press-and-hold mic with level meter,
  status dot + elapsed counter + ✕ Cancel (checkpoints: post-Jev, pre-LLM,
  pre-speech), tiles (clock 24h, weather with click-for-my-location, next-
  sun-event-big), timers, replayable history (day-grouped dd.MM.yyyy, ▶
  replay, ↻ re-run, ✎ edit, 🗑 per entry/day/all), token prompt overlay
- Settings page: per-user keys + `LLM_MODEL` + `ALERT_MESSAGE` + token +
  ntfy topic in localStorage (paste-first, bulk `.env` import/export —
  mobile-paste-proof parser — server-side Test keys, keys-links section)
- Server-key quota: `SERVER_KEY_LIMIT` free turns, client-counted, at the
  limit the page auto-opens Settings
- Reconnect: backoff capped 8s, PTT triggers instant reconnect
- Favicon from `assets/icon.png` on both pages
- Fronts: NPM (80/81, DNS-01 cert, WS toggle) + cloudflared tunnel + Coolify
  — all proxies; server binds plain HTTP (`REMOTE_FRONT` in `.env`)

## Open (designed, not built)

1. **ESP32/Pico device actions** — `device_action` target, MQTT/serial:
   [../android/08-remote-mic-pc.md](../android/08-remote-mic-pc.md) §5
2. **Termux native client** — only needed for background/away-from-tunnel
   use; same folder §4
3. **Optional packaging** — PyInstaller exe (`--onefile --windowed`)
4. **Known trade-offs**:
   - KEV latency 4–13s/turn (0.8B CPU model) and occasional sub-gate
     confidences → mitigate with a lower temperature/bigger checkpoint or
     the `/permute` endpoint ([../jev-compatible.md](../jev-compatible.md) §2)
   - Spotify in-app volume maps to system volume (no Windows API for it)
   - Sleep hibernates if hibernation is enabled
   - Whisper `small.en` CPU — a GPU box could run `large-v3`
