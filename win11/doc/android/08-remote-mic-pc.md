# Termux phone as remote mic + PTT, Windows PC as the brain

Status: **the PC side is implemented** — `win11/siri.py --remote` serves the
WebSocket/HTTP turn server, and the served web page (§6) is the primary
client (live at the configured tunnel host on this PC). The Termux native
client (§4) remains optional/not built. The ESP32 extension (§5) is still
designed-only.

Instead of porting hey-jev *to* the phone, the phone becomes a **dumb
wireless headset with a push-to-talk button**, and the untouched Windows
build keeps doing everything (decisions, actions, Fish playback). Every
hard Android blocker disappears:

| Android blocker | This design |
| --- | --- |
| no PortAudio/sounddevice | phone just records (Termux recorder + ffmpeg) |
| no ctranslate2/faster-whisper | Whisper runs on the PC |
| phantom process killer | session only lives between PTT press and response |
| no wake word | PTT on the phone; PC keeps its own right-Alt PTT |
| no media keys/volume/dark mode | PC executes them locally |

## 1. Why this architecture wins on effort

The phone-side app is tiny: capture → send → play reply. The PC-side is one
server mode (`--remote`) around the existing `handle()`.

## 2. PC-side server mode (implemented)

`--remote`: accept audio (WebSocket or HTTP POST), run the existing
`handle()` with a say-redirect that returns the cached Fish wav instead of
playing locally, stream status events + cost + reply wav back. Details in
[09-web-only-client.md](09-web-only-client.md).

## 3. Transport options

### A. HTTP/WebSocket on the LAN (implemented, recommended)

Simplest, debuggable with curl, mDNS discovery, status events trivial.

### B. SSH

Termux `openssh`; zero new server code; ~0.5-1s setup latency per turn;
workable over Tailscale for away-from-home. With the existing cloudflared
tunnel, SSH's away-from-home role is mostly covered already.

### C. Bluetooth

Phone as A2DP/HFP device → PC sees it as mic+speaker → **zero code changes**
(only `--device` selection). Weak link: Windows BT mic profiles (HFP quality,
reconnection). Worth a 30-minute experiment.

**Ranking: A (implemented) first, B for away-from-home, C as a zero-code
experiment.**

## 4. Phone-side client sketch (Termux) — optional now

```
~/hey-jev-client/
  ptt.sh              # Termux:Widget entry
  client.py           # record → POST /turn → play
```

```python
import urllib.request

PC = "http://heyjev.local:8765"
TOKEN = open("~/.heyjev-token").read().strip()
# record (termux-microphone-record), decode (ffmpeg to f32le 16k), then:
req = urllib.request.Request(PC + "/turn", data=pcm,
    headers={"Content-Type": "application/octet-stream",
             "Authorization": f"Bearer {TOKEN}"})
wav = urllib.request.urlopen(req, timeout=120).read()
open("/tmp/reply.wav", "wb").write(wav)
```

PTT release is the UX wrinkle (widget taps) — the web page (§6) solves it
with real press-and-hold.

## 5. ESP32 / Pico / Arduino — sensors, LEDs, motors as new Jev actions

Extend `QUESTIONS` (`device_action`: light on/off, color, servo, sensor
read), `REPLIES`, and the ACTIONS table; the PC forwards to the MCU.
Transports: USB serial (pyserial — most reliable), Wi-Fi + MQTT
(multi-device, sensor streaming), plain HTTP, BLE. Protocol shape:

```
→ {"action":"light","color":"#00ff88","on":true}
→ {"action":"read","sensor":"temp"}
← {"ok":true,"value":21.6}
```

Hardware: ESP32 (Wi-Fi+BLE) > ESP8266; Pico W (MicroPython, solid USB
serial); Arduino UNO-class needs level shifting. Security: LAN-only, token;
never port-forward MCU endpoints.

## 6. Web page client (implemented)

The PC serves a single-page PTT interface: press-and-hold button,
`getUserMedia` (one permission prompt), AudioWorklet downsampling to 16 kHz,
WebSocket streaming, reply audio played back. PWA-addable. Zero Termux
tooling — details in [09-web-only-client.md](09-web-only-client.md).

## 7. Latency budget

| Stage | ms |
| --- | --- |
| recorder start (Termux) | 300–800 |
| stop + ffmpeg | 300–600 |
| transfer (5 s f32 ≈ 640 KB, LAN) | 50–150 |
| Whisper on PC | 400–900 |
| Jev/KEV decision | 300–13 000 (KEV CPU is the slow pole) |
| Fish TTS | 0 (cached) – 3 000 |
| wav back + player | 150–400 |
| **total, cached** | **≈ 1.5–2.5 s** (KEV: up to ~15 s) |

## 8. What stays impossible

- Away-from-home without a tunnel (Tailscale optional).
- Wake word on the phone (Termux can't own the mic; the web page is
  foreground-only).

## 9. Implementation order

1. ~~PC `--remote` HTTP server~~ **done**
2. ~~Web page client~~ **done**
3. Status events + ~~elapsed counter~~ **done**
4. ESP32 over USB serial with a `light` action → MQTT for sensors
5. Optional Tailscale/SSH for outside-the-house
