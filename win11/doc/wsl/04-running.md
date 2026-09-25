# Running on WSL Ubuntu

All commands assume the repo root inside WSL.

## Modes

```bash
.venv/bin/python siri.py --text "set a timer for 5 minutes"
.venv/bin/python siri.py --wake
.venv/bin/python siri.py
```

`--ui` is macOS-only. The trace prints to the terminal; below the gate she
asks you to repeat.

## Playback

The port's `play_wav` uses sounddevice → PortAudio → ALSA → (asound bridge)
→ WSLg PulseAudio → Windows mixer. The old `afplay`/paplay shims are only
needed for the *original* repo code.

## Push-to-talk on WSL — read this first

pynput needs X11; WSLg runs Wayland + XWayland (`DISPLAY=:0`). X11 global
keyboard grabs only see keys **while an X11 window has focus** — so PTT
works only with a WSLg terminal focused. **`--wake` has no such dependency**
(it listens through the mic) — prefer it.

## Recommended test sequence

```bash
paplay /usr/share/sounds/alsa/Front_Center.wav
parecord --channels=1 --rate=16000 t.wav && paplay t.wav
.venv/bin/python siri.py --text "set a timer for 10 seconds"
.venv/bin/python siri.py --wake
```

App commands answer "unsupported" until the action layer is ported — the
roadmap routes them at the Windows host through `powershell.exe` interop.
