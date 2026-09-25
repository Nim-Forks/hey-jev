# Hey Jev on WSL2 Ubuntu

Status: **runs today in terminal mode**, with two WSL-specific soft spots:
microphone input and the global push-to-talk hotkey both depend on WSLg
(PulseAudio / XWayland). Everything HTTP — Jev, Fish TTS, OpenRouter — and
everything pure Python — Whisper, timers — works the same as on Windows.
Note: the port's `play_wav` (sounddevice) replaces the old afplay problem;
point its output at the WSLg PulseAudio server. If you want the most
reliable experience, prefer [../win11](../win11/README.md).

## Files in this folder

1. [01-prerequisites.md](01-prerequisites.md) — WSL2/WSLg checks, apt packages
2. [02-install.md](02-install.md) — clone inside WSL home, venv, ALSA-to-PulseAudio bridge
3. [03-api-keys.md](03-api-keys.md) — the mandatory `.env` file
4. [04-running.md](04-running.md) — modes, paplay shim note, hotkey caveats
5. [05-porting-roadmap.md](05-porting-roadmap.md) — powershell.exe interop strategy, backend override
6. [06-troubleshooting.md](06-troubleshooting.md)

## What works / what does not, as-is

| Feature | State on WSL today |
| --- | --- |
| Jev decisions, timers, LLM answers, TTS caching | works |
| Whisper STT | works (CPU int8) |
| Mic recording | works **if** WSLg PulseAudio mic passthrough is healthy — test with `parecord` first |
| Right-Alt push-to-talk | only while an X11 window has focus (XWayland); `--wake` is the reliable option |
| `--text "..."` one-shot | works |
| Audio replies | work via sounddevice once the asound bridge routes to WSLg PulseAudio |
| Controlling **Windows** apps/volume from WSL | not ported; roadmap routes actions through `powershell.exe` interop |
| Status window (`--ui`) | no — AppKit/tkinter under X11 possible but not the target |

Same blocking bugs as on Windows for the *original repo*: `pyobjc` cannot
install (`requirements.txt:8`) and the Mac `speak()` calls `afplay` — the
port fixes both; these docs cover running either.
