# Termux MVP — push-to-talk hey-jev on a phone

The fastest path: keep the Python brain untouched, swap only audio/STT,
accept push-to-talk-only. **Still research — not implemented** (the
implemented phone path is the web remote: [09-web-only-client.md](09-web-only-client.md)).

## What you get

- One turn per press: tap widget → speak → release → answer out loud.
- Timers/reminders while the Termux session is alive.
- Jev/KEV decisions, Fish TTS replies, LLM answers — identical behavior.
- Volume via `termux-volume`; app open via intents.

## What you do NOT get

- Always-on wake word; global media transport for Spotify; dark mode/lock;
  reliability guarantees (Android fights background Python).

## Install (Termux from F-Droid, not Play Store)

```bash
pkg update
pkg install python ffmpeg clang cmake ninja git termux-api
pip install requests python-dotenv numpy   # no sounddevice, no faster-whisper
```

Companion apps from F-Droid: **Termux:API**, **Termux:Widget**. Grant the
microphone permission.

## Keys

`~/.env` in the project dir — same names as everywhere
([../win11/03-api-keys.md](../win11/03-api-keys.md)).

## STT: whisper.cpp instead of faster-whisper

```bash
git clone https://github.com/ggml-org/whisper.cpp ~/whisper.cpp
cd ~/whisper.cpp
cmake -B build -DGGML_OPENMP=OFF && cmake --build build -j
./models/download-ggml-model.sh base.en
```

Python access via raw `ctypes` or `pywhispercpp`; keep the
`transcribe(audio, prompt)` signature.

## Audio: record to file, decode, feed

```bash
termux-microphone-record -f /tmp/utt.m4a -e aac -l 15   # start
termux-microphone-record -q                              # stop
ffmpeg -y -i /tmp/utt.m4a -ar 16000 -ac 1 -f f32le /tmp/utt.pcm
```

Playback of Fish's wav: `termux-media-player play reply.wav` or
`mpv --ao=audiotrack reply.wav`. `termux-tts-speak` uses the Android TTS
voice — don't (defeats Fish).

## Trigger: Termux:Widget

Two-line shell script in `~/.shortcuts/`, long-press home → Widget → drop it.
MVP release trigger: fixed max length or a notification action.

## Actions that survive on Termux

| Action | Termux path |
| --- | --- |
| volume up/down/mute/set | `termux-volume music <0-15>` |
| open app | `termux-am start -n <pkg/activity>` |
| local media | `termux-media-player play/pause <file>` |
| timers | unchanged Python + `termux-wake-lock` |
| everything else | `unsupported` line |

## Structure (when implemented)

```
android/termux/
  siri.py       # imported unchanged from ../../win11
  recorder.py   # termux-microphone-record + ffmpeg
  whisperc.py   # ctypes/pywhispercpp loader
  player.py     # termux-media-player / mpv
  actions.py    # ACTIONS replacements
  ptt.py        # entry point
```
