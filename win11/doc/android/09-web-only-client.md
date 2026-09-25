# Web-only option: the browser IS the client

Status: **implemented and live** — `win11/siri.py --remote` + the served
page (this PC: NPM front + cloudflared tunnel). This doc was the design
source; deviations that shipped are noted inline. The browser is a
**zero-install client platform**: any device with a browser and a mic
becomes a hey-jev remote with nothing installed.

## 1. The idea

The PC serves a single HTML page. The browser captures the mic
(`getUserMedia`, one permission prompt), an AudioWorklet resamples to
16 kHz mono float32, a WebSocket streams it to the PC, the same socket
streams back status events and the reply wav (played via WebAudio). On a
phone, "Add to Home Screen" makes it an app icon that opens straight into a
press-and-hold PTT button.

## 2. Why this is the best PTT experience

- **Real press-and-hold** (`pointerdown`/`pointerup`) — no widget taps.
- **Mic permission handled by the browser** — one prompt.
- **Zero install, zero build** — the page ships from the PC itself.
- **Every device** — phone, tablet, laptop, wall kiosk.
- **Status UI for free** — state dot, Jev trace, timers, cost badge live
  from the same socket.

## 3. Constraints

- **Foreground only.** Background tabs lose the mic; iOS Safari stops
  capture on lock. This is a walk-over remote, not always-listening. (The
  server-owner's ntfy channel covers closed-page alerts.)
- **HTTPS or localhost for mic access.** Solved on this PC via cloudflared +
  NPM (trusted certs); self-signed/mkcert are the LAN-only fallbacks.
- **Audio codec**: raw 16 kHz float32 PCM over WS (640 KB per 5 s — trivial
  on LAN); opus via MediaRecorder is the off-LAN option.
- **iOS Safari**: worklet + getUserMedia work; playback needs a gesture
  first (the page unlocks audio on PTT press).

## 4. Server design (as implemented)

```
GET  /              → PTT page        GET  /settings → keys page
GET  /app.js        → client logic    GET  /worklet.js → resampler
GET  /health        → 200 ok          GET  /favicon.png → icon
WS   /ws            → auth {token|keys, memory, uses, ntfy} →
  audio-start / binary PCM chunks / audio-end →
  heard → state events → reply line → wav bytes → cost
  text {text}        → typed turn      replay {text} → cached wav
  cancel             → stop at next checkpoint
  timers / tiles     → live countdowns / clock+weather+sun
  weather-at {lat,lng} → location weather for the tile
  memory-sync / ntfy-sync → per-device localStorage state
POST /turn          → raw PCM → wav (+ X-Events, X-Cost)
POST /test-keys     → server-side decision ping with submitted keys
```

## 5. The page (as implemented)

Text box (top) → HOLD TO TALK (press-and-hold, level meter) → status (dot,
colors, elapsed counter, ✕ cancel) → heard/she-said line + cost badge →
tiles (24h clock, weather with click-for-my-location via geolocation,
sunrise/sunset with the next event big) → timers → history accordion
(dd.MM.yyyy day groups; ▶ replay, ↻ re-run, ✎ edit, 🗑 per entry/day/all;
localStorage, 20 entries) → Settings.

## 6. Settings page

Per-user API keys + `LLM_MODEL` + `ALERT_MESSAGE` + shared token + ntfy
topic — all in localStorage, **paste-first** (password-manager friendly,
no retype, eye toggles), bulk `.env` import/export with a mobile-paste-proof
parser (ntfy-style collapsed lines auto-parsed), server-side "Test keys",
keys-links section (fish.audio, typesafe.ai, openrouter.ai). Keys travel
per connection only; the server never persists them.

## 7. Verdict

Implemented. The combo that shipped: `--remote` + this web page as the
primary client, NPM + cloudflared fronts (token-gated), ESP32 path next
([08-remote-mic-pc.md](08-remote-mic-pc.md) §5), Termux client only if
background/away-from-tunnel use ever matters.
