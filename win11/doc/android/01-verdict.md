# Android verdict — what ports, what's blocked

Scope: porting the hey-jev port to Android. As of 2026-09.

## What ports with zero or near-zero changes

| Component | Why it ports |
| --- | --- |
| `jev()` decision client | plain `requests` POST; the KEV override carries over |
| Fish TTS fetch + disk cache | plain HTTPS + file writes |
| Timers/reminders logic | pure Python |
| LLM fallback | plain HTTPS |
| Wake regex, duration parsing, REPLIES, `decide()`/`split_actions()` | pure Python |

~80-90% of the decision/brain code is reusable unchanged.

## Hard blockers (the existing stack cannot run)

1. **sounddevice / PortAudio** — PortAudio's Android/OpenSL backend is
   abandoned; no Termux package; no Android wheels.
2. **faster-whisper / ctranslate2** — no Android/Bionic artifacts on PyPI;
   Termux's Bionic Python refuses manylinux wheels anyway.

## Soft blockers

3. **Global media-key injection, dark mode, screen lock, app management** —
   Android only allows them from a real app (intents, `MediaSessionManager`,
   `UiModeManager`, Accessibility).
4. **Always-on wake word** — Android 12+ phantom process killing; Android 14
   `FOREGROUND_SERVICE_MICROPHONE` requirement. Native-app feature.
5. **PTT hotkey** — no global key to grab; use a widget, notification button,
   headset hook — or the implemented web remote.

## The two viable architectures

### A. Termux MVP — push-to-talk only (days)

`termux-microphone-record` → `ffmpeg` → 16 kHz mono wav → whisper.cpp
(built in Termux) → unchanged Python brain → Fish TTS wav →
`termux-media-player`. No wake word, no media transport, no dark mode/lock.

### B. Kotlin + Chaquopy hybrid — the realistic ceiling (weeks)

Small Kotlin app: foreground service (`microphone` type) owns `AudioRecord`
capture and a Vosk wake word; transcripts handed to the unchanged Python
brain via Chaquopy; actions via real Android APIs; Fish TTS via `MediaPlayer`.
Design: [05-native-port-design.md](05-native-port-design.md).

## Not viable

- **Kivy/Buildozer**: no ctranslate2/faster-whisper/PortAudio recipes — same
  blockers inside a worse build chain.
- **Pydroid 3**: text-mode prototype only.
