# Android troubleshooting (research notes)

Problems that WILL come up on the Termux MVP path. Nothing implemented yet.

## `pip install sounddevice` fails / PortAudio not found

Expected — PortAudio doesn't support Android. Uninstall; capture goes
through `termux-microphone-record` + `ffmpeg`.

## `pip install faster-whisper` fails (ctranslate2)

Expected — no Bionic wheels. Use whisper.cpp in Termux.

## `pip install numpy` fails on Termux

Use the Termux-repo build: `pkg install python-numpy` (PyPI manylinux wheels
are refused on Bionic).

## Phantom process killer kills the Python process (Android 12+)

1. `adb shell "settings put global settings_enable_monitor_phantom_procs false"`
2. or `adb shell device_config put activity_manager max_phantom_processes 2147483647`
3. Battery optimization → Unrestricted for Termux.
4. Hold `termux-wake-lock` while the session lives.

## `termux-microphone-record` records silence

- Termux:API app needs the mic permission.
- Another app holding the mic blocks it.
- Verify: `termux-microphone-record -f /tmp/t.m4a -l 3` → `termux-media-player play /tmp/t.m4a`.

## ffmpeg decode gives noise/wrong speed

Force everything: `ffmpeg -y -i in.m4a -ar 16000 -ac 1 -f f32le out.pcm`.
Check PCM endianness assumption (f32le vs f32be).

## Whisper is too slow

- Drop to `tiny.en`; 4 threads (`-t 4`).
- Keep the model loaded in a resident process, not per turn.

## Fish TTS plays nothing via `termux-media-player`

Check the cached file isn't 0 bytes/truncated; fall back to
`mpv --ao=audiotrack`.

## Timers don't fire when the screen is off

Python thread frozen on suspend. `termux-wake-lock` helps; long timers
(>15 min) are unreliable — the native design routes them via AlarmManager.

## KEV/Jev 401 from the phone

- `.env` (`~/` project dir, no quotes, exact name).
- `KEV_URL` set but `KEV_API_KEY` empty → silently stays on Typesafe
  (`USE_KEV` requires both).

## Wake word (Termux): it just isn't there

Recorder latency + no streaming VAD + phantom killing. Wake word needs the
native design ([05-native-port-design.md](05-native-port-design.md)).
