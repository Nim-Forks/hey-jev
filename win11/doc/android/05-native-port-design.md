# Native port design — Kotlin foreground service + Chaquopy hybrid

Design doc — nothing implemented. If the goal is the best pure-Android
product without Python reuse, rewrite in Kotlin
([04-packaging-options.md](04-packaging-options.md) option D).

## Shape

```
Kotlin app
├── WakeService (foreground service, type="microphone")
│     ├── AudioRecord: 16 kHz mono float32, 100 ms blocks   ← Recorder logic 1:1
│     ├── Vosk keyword spotting ("hey jev")                 ← replaces the mic-loop pre-filter
│     └── on phrase end: hand PCM → Brain.transcript(text)
├── Brain (Chaquopy-embedded Python)
│     ├── unchanged decision core: jev(), decide(), split_actions(),
│     │   run_timer(), REPLIES, parse_duration(), ask_llm(), WAKE regex, GATE
│     └── API: handle(text) -> (reply_line, [actions])
├── ActionRouter (Kotlin)                                    ← replaces ACTIONS
│     ├── app_open: intents (spotify: URI, package launch, …)
│     ├── volume: AudioManager.setStreamVolume (STREAM_MUSIC)
│     ├── media transport: MediaSessionManager + MediaController dispatch
│     │     (needs NotificationListenerService binding)
│     ├── dark mode: UiModeManager (API 31+)
│     ├── lock: AccessibilityService GLOBAL_ACTION_LOCK_SCREEN / DevicePolicyManager
│     ├── sleep: no equivalent — map to screen-off or drop
│     └── timers: AlarmManager.setExactAndAllowWhileIdle + full-screen intent
├── Speaker (Kotlin)
│     ├── Fish TTS HTTPS POST (same headers, model: s2.1-pro-free)
│     ├── cache under context.cacheDir (sha1 pattern from fetch_tts)
│     └── MediaPlayer on STREAM_MUSIC
└── UI: status overlay/notification (state colors, timer rows, mode switch)
```

## Why the split at `handle(text)`

Everything Android-shaped sits *before* the transcript and *after* the
decision. `handle()` is the seam: input = transcript string, output = reply
line + action list. The Python side never touches audio/processes/windows;
the Kotlin side never parses commands.

## Wake word flow

1. `WakeService` streams mic blocks into Vosk's small model.
2. On "hey jev" (Vosk partial + the existing `WAKE` regex re-check on the
   final transcript), answer "Yes?" (pre-cached Fish wav), open the command
   window: 6 s (`WAKE_WINDOW`).
3. Phrase-end detection: same RMS/silence constants as the desktop Recorder
   (0.8 s pause, 15 s cap).

## Permissions matrix

| Permission | Type | For |
| --- | --- | --- |
| RECORD_AUDIO | runtime | capture |
| POST_NOTIFICATIONS | runtime (13+) | FGS notification, timer alerts |
| FOREGROUND_SERVICE_MICROPHONE | manifest (14+) | background listening |
| MODIFY_AUDIO_SETTINGS | normal | volume |
| QUERY_ALL_PACKAGES / `<queries>` | manifest | app_open resolution |
| NotificationListenerService binding | user grants | media transport |
| AccessibilityService | user grants | lock screen |
| SCHEDULE_EXACT_ALARM | user grant (14+) | timers |

The two Settings-grants are the Android analogues of the Mac's Accessibility
permission — document them in first-run.

## What stays in Python (via Chaquopy)

- `jev()` + KEV override (env from BuildConfig/config bridge).
- `decide()`, `pick_action()`, `split_actions()` — untouched.
- Timers: keep the Python loop for conversation ("how long is left?"), but
  mirror due-timers into `AlarmManager` so they fire even if the Python
  thread was frozen.
- `REPLIES`, warm-cache list — Kotlin Speaker requests cached paths by text
  hash.

## MVP milestone order

1. Chaquopy skeleton: `handle("set a timer for 5 minutes")` from a button,
   Fish wav plays.
2. PTT button → AudioRecord → whisper.cpp JNI (or SpeechRecognizer) →
   `handle()`.
3. Volume + app_open actions.
4. Vosk wake word + `WAKE_WINDOW`.
5. Media transport, dark mode, lock, AlarmManager timers, status UI.
