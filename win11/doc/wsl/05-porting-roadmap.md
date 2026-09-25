# Porting roadmap (WSL Ubuntu)

Items 1-2 are shared with the Windows port (already implemented in
`win11/siri.py`). Item 3 is the WSL-specific part.

## 1. requirements.txt — make it install off the Mac

```
pyobjc-framework-Cocoa>=11.0; sys_platform == "darwin"
```

## 2. Audio playback — implemented in the port

`speak()`/`play_wav()` use sounddevice, not afplay — on WSL the output flows
through the asound bridge → WSLg PulseAudio → Windows mixer. Timer chime is
`winsound` on Windows; on WSL use a bundled wav or `print("\a")`.

## 3. Actions — route them to the Windows host via interop

Linux-native tools control the wrong world from WSL (`pactl` hits the WSLg
sink, MPRIS sees no Windows players). Route every system action through
`powershell.exe`:

```python
def sh(*cmd):
    if shutil.which("powershell.exe"):
        subprocess.run(["powershell.exe", "-NoProfile", "-Command", *cmd], ...)
```

Then reuse the Windows action table (see
[../win11/05-porting-roadmap.md](../win11/05-porting-roadmap.md)): media
keys and volume via SendKeys/AudioDeviceCmdlets, `rundll32` lock/sleep,
registry + `WM_SETTINGCHANGE` for dark mode, `Start-Process`/`Stop-Process`
for apps. Keep the same action keys and reply keys. Latency: ~100-300 ms per
interop call — fine for app control. Fallback: if `powershell.exe` is
missing, degrade to timers/questions only.

## 4. UI — replace AppKit

- Headless (current state) is fine to ship.
- tkinter works under WSLg/XWayland (`DISPLAY=:0`).

The state protocol is unchanged: `run_voice_assistant(notify, controls,
mode)` — any UI is a producer/consumer of the same callbacks.

## 5. Secrets — already done

`.env` is the supported path (chmod 600). Optionally `keyring` with the
Secret Service later.

## 6. Decision backend override — already done

`JEV_URL`-equivalent: the port ships `KEV_URL`+`KEV_API_KEY` and the
OpenRouter fallback ([../jev-compatible.md](../jev-compatible.md)).

## Explicitly out of scope / deferred

- `spotify_volume_*` — needs Spotify Web API OAuth
- ALSA/PipeWire native audio — WSLg PulseAudio is the supported route
- Wayland-native global hotkeys — platform limitation; use `--wake`
