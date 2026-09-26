# Running on Linux

## Modes

```bash
.venv/bin/python siri.py --text "set a timer for 5 minutes"
.venv/bin/python siri.py --wake          # needs X11 + mic
.venv/bin/python siri.py --remote        # the systemd service runs this
systemctl restart hey-jev                # after .env / code changes (sudo if needed)
sudo journalctl -u hey-jev -f            # live Jev trace
```

## What she can do on Linux

**Commands** (Jev fan-out → Linux action layer): open/quit apps (desktop ids
+ `pkill` — Spotify, Slack, Chrome, VS Code, Files, Edge, Text Editor,
Terminal), volume up/down/mute/set (pactl → PipeWire), media
play/pause/next/previous (playerctl → MPRIS, reaches Spotify Linux),
dark mode (gsettings — needs a GNOME session), lock/sleep (loginctl /
systemctl suspend). Apps not installed → graceful `unsupported`.

**Timers & alarms**: same as Windows — "set a timer for 5 minutes",
"remind me in 20 minutes to call Mum", "set an alarm for 7:30 am" (daily),
"cancel my alarm", "cancel all". Persisted to `timers.json`. Alerts: chime
(freedesktop sound via paplay) + spoken line + ntfy push + web page alert.

**Free-API skills**: identical to Windows — weather, "will it rain in X",
sunrise/sunset (24h local of the *queried place*), currency, Wikipedia,
jokes, news; LLM fallback (`LLM_MODEL`) with Jev-gated context: current
time, machine status (host/uptime/load/RAM/disk/battery/running apps via
/proc), memory facts.

**Memory** (web remote, per device): same flow — "remember that…", recall,
forget; stored in the connecting browser's localStorage.

**Languages (STT)**: `install.sh` offers extra languages (`WHISPER_LANGUAGES`
in `.env`, e.g. `en,hr,de`). With any non-English entry, the multilingual
`small` model (~470 MB) is downloaded and Whisper **auto-detects** the
spoken language — she replies in it too (the LLM mirrors the language).
English-only setups keep `small.en`.

## The web remote

- systemd service runs `siri.py --remote` on `127.0.0.1:8765`
- cloudflared tunnel (already running on this box) exposes it — the
  `heylinux` ingress line in `~/.cloudflared/config.yml` + the DNS route
  (see [02-install.md](02-install.md) §6 for the flow)
- The served page is identical to the Windows one: PTT, typed input,
  cancel, tiles, history, Settings (per-user keys, ntfy topic, token) —
  per-device localStorage applies
- Token gate: with `REMOTE_TOKEN` set, a wrong/missing token shows an
  inline "Access token required" prompt

## Timer alerts — all channels

| Channel | Mechanism |
| --- | --- |
| machine speakers | chime + spoken line (works headless — PipeWire user session) |
| ntfy (server default) | `NTFY_URL` |
| ntfy (per device) | topic set in Settings, stored per browser |
| open web pages | `timer-fired` → vibrate + notification + spoken line |

## STT models

| Setup | Model | Size | Notes |
| --- | --- | --- | --- |
| English only (default) | `small.en` | ~250 MB | ~1-2 s per utterance |
| `WHISPER_LANGUAGES` has non-en entries | multilingual `small` | ~470 MB | language auto-detected per turn |

Both live in `~/.cache/huggingface`; `whisper_spec()` picks per boot from
`WHISPER_LANGUAGES` — if the multilingual model is missing it warns and
falls back to English-only.

## Latency notes (this machine, KEV backend)

| Stage | Typical |
| --- | --- |
| KEV decision | 4–16 s (0.8B CPU model — the slow pole) |
| GLM answer (effort=low) | 1.5–7 s |
| Fish TTS | cached 0 / uncached 1–6 s |

The elapsed counter in the status line shows progress so waiting never
looks frozen.

## PTT specifics

- Requires X11 (`pynput`); headless boxes print a note and the service
  stays on `--remote`.
- Mic: PipeWire default source — `install.sh` sets it to the real mic;
  `pick_input()` skips monitors and prefers mic-named devices.
