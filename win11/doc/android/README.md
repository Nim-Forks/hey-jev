# Android

Can hey-jev run on Android? Short answer: **the brain yes, the body no.**
Everything HTTP or pure Python (Jev/KEV decisions, Fish TTS, timers, LLM
fallback) ports directly. Everything touching the OS (audio capture,
playback, STT runtime, actions, global hotkeys) hits platform walls and
needs replacing, not porting. The **recommended** path — phone as remote
mic/PTT for the PC — is already implemented as the win11 `--remote` server
+ web page ([08](08-remote-mic-pc.md), [09](09-web-only-client.md)).

- [01-verdict.md](01-verdict.md) — what ports, what's blocked, viable architectures
- [02-termux-mvp.md](02-termux-mvp.md) — Termux push-to-talk MVP
- [03-audio-and-stt.md](03-audio-and-stt.md) — the two hard blockers and replacements
- [04-packaging-options.md](04-packaging-options.md) — Termux vs Kivy vs Chaquopy vs Kotlin
- [05-native-port-design.md](05-native-port-design.md) — Kotlin FGS + Chaquopy hybrid design
- [07-yodaos-rokid.md](07-yodaos-rokid.md) — Rokid AIUI glasses (JS agent option)
- [08-remote-mic-pc.md](08-remote-mic-pc.md) — **implemented on the PC side**: phone as remote mic
- [09-web-only-client.md](09-web-only-client.md) — **implemented**: browser IS the client
- [06-troubleshooting.md](06-troubleshooting.md)

## The one-paragraph version

Two hard blockers make the existing Python stack unportable as-is:
**sounddevice/PortAudio does not support Android** and **faster-whisper
needs ctranslate2, which has no Android/Bionic build**. Android 12+ kills
long-running background processes and Android 14 requires a microphone-typed
foreground service for background listening — so always-on wake-word
listening is a native-app feature. The implemented answer: keep the brain on
the PC, serve a PWA-style web page, let any phone browser be the mic
([09](09-web-only-client.md)). Rokid AIUI glasses are the other JS-agent
route ([07](07-yodaos-rokid.md)).
