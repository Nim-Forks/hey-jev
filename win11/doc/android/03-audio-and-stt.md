# The two hard blockers: audio and STT — and their replacements

## Blocker 1: sounddevice / PortAudio

PortAudio's Android/OpenSL backend is abandoned; no Termux package; pip
refuses manylinux wheels on Bionic. Native paths are AAudio (API 26+) and
OpenSL ES — neither exposed to Termux Python without JNI.

### Replacement: record-to-file + decode

`termux-microphone-record` (MediaRecorder): aac/m4a, amr_wb, amr_nb, opus;
`-r` rate, `-l` length, `-q` stop. Decode: `ffmpeg -i in.m4a -ar 16000 -ac 1
-f f32le out.pcm` — exactly the float32 16 kHz mono the pipeline expects.
Cost: ~0.5-1 s per turn, **no streaming VAD** — push-to-talk only.

### Replacement (native app)

`AudioRecord` with `ENCODING_PCM_FLOAT`, 16 kHz, mono — the desktop Recorder
logic ports 1:1. Background capture needs a foreground service with the
`FOREGROUND_SERVICE_MICROPHONE` type (mandatory since Android 14).

## Blocker 2: faster-whisper / ctranslate2

No Android/Bionic wheels on PyPI; Termux pip would refuse them anyway;
source-build against Bionic is research territory; no p4a recipe.

### Replacement: whisper.cpp

Builds natively in Termux (`cmake` + `clang`, `-DGGML_OPENMP=OFF`).
`base.en` (~150 MB) is the phone sweet spot; `small.en` is 2-4x slower than
real-time on mid-range CPUs. Python via `pywhispercpp` or `ctypes` — keep
`transcribe(audio, prompt)`.

In a native app: whisper.cpp JNI, or Android `SpeechRecognizer` (offline
decent since Android 13; no custom wake-word API — `HotwordDetector` is
system-only).

### Wake word specifically

- **Vosk**: official Android AAR, ~50 MB small model does "hey jev" keyword
  spotting on-device.
- **Porcupine** (Picovoice): commercial-but-free-tier, custom keywords.
- whisper.cpp tiny/base looping = battery-hungry fallback.
- The desktop `WAKE` regex still applies downstream of the detector.

## What survives untouched

The moment a WAV exists on disk and a transcript comes back, everything
downstream is platform-independent: `jev()` → `decide()` → actions →
`fetch_tts()` → play.
