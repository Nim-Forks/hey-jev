# Running on Windows 11

All commands assume you are in `win11/` and use the venv Python directly
(no activation needed).

## Modes

```powershell
# one turn from text, no mic (best first test)
.venv\Scripts\python.exe siri.py --text "set a timer for 5 minutes"

# always listening, say "Hey Jev" (mic + Whisper, no hotkey needed)
.venv\Scripts\python.exe siri.py --wake

# push-to-talk on right Alt (pynput global listener)
.venv\Scripts\python.exe siri.py

# status window + tray icon (like the Mac app)
.venv\Scripts\python.exe siri.py --ui

# web remote: phone/browser is the mic (what this PC actually uses)
.venv\Scripts\python.exe siri.py --remote
# or simply:  powershell -File restart-remote.ps1
```

Mic selection (`--wake`/PTT only):

```powershell
.venv\Scripts\python.exe siri.py --list-devices
.venv\Scripts\python.exe siri.py --wake --device 1     # index or name
```

If Windows has **no default input device**, the port auto-picks the first
available microphone and says so in the log; `--device` overrides. This PC
currently has **no microphone endpoint at all** (only "Remote Audio",
output-only) — which is why the web remote is the primary interface here.

## What she can do

**Commands** (Jev fan-out → Windows action layer): open/quit apps (Spotify,
Slack, Chrome, VS Code, Explorer, Edge, Notepad, Terminal), volume
up/down/mute/set (WASAPI via inline C#), media play/pause/next/previous
(pynput global media keys — reaches Spotify without focus), dark mode
(registry + live broadcast), lock/sleep (`rundll32`; sleep hibernates if
hibernation is on).

**Timers & alarms**: "set a timer for 5 minutes", "remind me in 20 minutes
to call Mum", "set an alarm for 7:30 am" (daily, self-rescheduling),
"cancel my alarm", "cancel all". Persisted to `timers.json` — they survive
restarts; missed reminders are pushed once on startup. Alerts: PC chime +
spoken line, phone push (ntfy), and page alert (vibrate/notify/speak on any
open web remote).

**Free-API skills**: "weather in berlin", "will it rain in paris" (verdict +
peak hour), "when is sunrise in berlin" (24h local), "how many dollars is
100 euros", "who is Ada Lovelace" (Wikipedia; "who wrote Hamlet" falls back
to the LLM), "tell me a joke", "give me the news" (BBC world / tech).

**Questions**: anything else goes to the LLM (`LLM_MODEL`) with context only
when Jev says it's needed: current time (`needs_time`), machine status
(`needs_machine` — uptime, CPU, RAM, disk, battery, running apps), and your
memory facts.

**Memory** (web remote, per device): "remember that my sister's name is
Anna" → stored in that browser's localStorage; "what's my sister's name?",
"what do you remember about me", "forget about my sister", "forget
everything". Facts ride every LLM answer on that device.

## The web remote (`--remote`)

- **Page**: on it, top to bottom: typed-command box → HOLD TO TALK
  (press-and-hold, browser mic; level meter while held) → status with live
  elapsed counter and ✕ Cancel → tiles (clock 24h, weather — click for
  your location, next sun event big) → timers → history accordion
  (per-day dd.MM.yyyy, ▶ replay, ↻ re-run, ✎ edit, 🗑 delete per entry/day/
  all) → Settings.
- **Settings page** (`/settings`): per-user API keys + `LLM_MODEL` +
  `ALERT_MESSAGE` + `REMOTE_TOKEN` + ntfy topic in localStorage (paste-only
  fields, bulk `.env` import/export incl. `NTFY_URL`, server-side
  "Test keys", keys-links section).
- **Token gate**: with `REMOTE_TOKEN` set, a bad/missing token shows an
  inline "Access token required" prompt — paste once, stored per device.
- **Protocol**: WebSocket turns (audio-start → PCM chunks → audio-end →
  heard/state events → wav bytes → cost), HTTP `POST /turn` for curl/Termux
  (raw PCM → wav, `X-Events` + `X-Cost` headers), `GET /health`.
- **Cancel**: the ✕ stops the turn at its next checkpoint (post-Jev, pre-LLM,
  pre-speech); the server resets state and answers Ready.
- **Costs**: shown as a badge (never spoken): Jev + LLM per turn, typically
  $0.00002–0.00006.
- **Key quota**: clients using the server's Fish key get `SERVER_KEY_LIMIT`
  free turns (client-counted); at the limit the page auto-opens Settings.

## Latency budget (this PC, KEV backend)

| Stage | Typical |
| --- | --- |
| KEV decision | 4–13s (0.8B CPU model — the slow pole) |
| GLM answer (effort=low) | 1.5–7s |
| Fish TTS | cached: 0 / uncached 1–6s |
| Web round trip | <1s |

The elapsed counter in the status line shows progress so waiting never
looks frozen.

## PTT specifics

- Right Alt (`keyboard.Key.alt_r`) is global on Windows; AltGr layouts
  report it as `alt_gr` — use `--wake` or change `PTT_KEY` in `siri.py`.
- No admin rights or Accessibility equivalent needed.
