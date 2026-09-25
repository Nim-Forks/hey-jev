# Docs: running Hey Jev off the Mac

Hey Jev is written for macOS, but only a thin layer of it is Mac-locked. The
brain (Jev/KEV decisions, Fish Audio TTS, whisper STT, timers, skills,
memory) is portable; the body (actions, audio, UI) was ported per platform.

- [win11/](win11/) — Windows 11. **Implemented and running daily**, including
  the web remote: phone/browser mic + PTT, typed input, cancel, tiles,
  replayable history, memory, free-API skills, alarms, ntfy push, three
  decision backends.
- [wsl/](wsl/) — WSL2 Ubuntu with WSLg. The port's playback (`play_wav`)
  works there too; mic input and global hotkeys depend on WSLg
  (PulseAudio/XWayland) and stay the flakiest links.
- [android/](android/) — Android research: two hard blockers (PortAudio,
  ctranslate2) mean no direct port; Termux MVP vs Kotlin+Chaquopy vs Rokid
  glasses. The **recommended** Android path — phone as remote mic — is
  implemented as the win11 `--remote` server + web page.
- [jev-compatible.md](jev-compatible.md) — the decision-backend wire
  contract; the app implements the KEV backend and the OpenRouter decisions
  fallback behind `.env` switches (no third-party endpoint URLs are stated
  in these docs by design).

## Implementation status

| Feature | Win11 port | WSL | Android |
| --- | --- | --- | --- |
| Jev + KEV + OpenRouter backends | yes | yes (same code) | yes (HTTP) |
| Whisper STT | yes | yes | needs whisper.cpp/Vosk |
| Fish TTS + cache | yes | yes | yes (HTTP) |
| Timers, alarms, persistence | yes | yes | termux: fragile |
| Skills (weather/rain, sunrise, currency, wiki, jokes, news) | yes | yes | yes |
| Memory (client localStorage) | yes (web) | — (web) | web |
| Audio playback | sounddevice | sounddevice | termux-media-player |
| App/device control | PowerShell/WASAPI/etc | Linux equivalents | interop |
| Web remote server + page | **implemented** | same code | n/a (is the client) |
| Status window + tray | tkinter/pystray | tkinter/X11 | native UI only |

The only docs that are still purely "research, not implemented" are the
Android-native paths ([android/04](android/04-packaging-options.md),
[android/05](android/05-native-port-design.md)).
