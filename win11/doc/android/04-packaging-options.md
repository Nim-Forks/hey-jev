# Packaging options, ranked

## A. Termux + termux-api scripts — effort: days

The MVP in [02-termux-mvp.md](02-termux-mvp.md). ~90% code reuse, no app
development; no wake word/media transport/dark mode; background reliability
is a fight. **Do this first — or skip entirely, the web remote (09) already
delivers phone-as-mic with zero install.**

## B. Kivy / Buildozer — effort: high, value: low

No ctranslate2/faster-whisper/PortAudio recipes; custom recipes mean
cross-compiling C/C++ to Bionic. Skip.

## C. Chaquopy in a Kotlin app — effort: moderate

Chaquopy embeds CPython 3.8-3.12 in an APK (free/open-source since v15,
2024). Kotlin owns everything Android-shaped; Python keeps the brain.
~80% reuse inside a real app. The realistic ceiling for keeping the Python
brain. Design: [05-native-port-design.md](05-native-port-design.md).

## D. Pure Kotlin rewrite — effort: highest, product: best

Rewrite the brain in Kotlin; same HTTP APIs (OkHttp). Full control:
foreground service with `FOREGROUND_SERVICE_MICROPHONE`, `AudioRecord` 16k
float32, Vosk/Porcupine wake word, `MediaSessionManager` +
`NotificationListenerService` for media, `AudioManager` volume,
`UiModeManager` dark mode (API 31+), Accessibility/device-admin lock,
intents for apps, `AlarmManager` + full-screen intent timers. No runtime in
the APK; single language; but desktop improvements must be mirrored by hand.

## Cross-cutting requirements

- Background mic: FGS with `microphone` type (Android 14+), persistent
  notification, runtime permission.
- Wake word always-on: only realistic via Vosk/Porcupine in a native FGS.
- Doze: hold the FGS during a turn; keep the TTS cache-on-disk pattern.
- HTTP APIs: no issues — standard CAs, plain HTTPS.

## Decision table

| | A. Termux | B. Kivy | C. Chaquopy | D. Kotlin |
| --- | --- | --- | --- | --- |
| Time to first turn | days | weeks | 1-2 weeks | 2-4 weeks |
| Python brain reuse | ~90% | ~90% (if it builds) | ~80% | 0% |
| Wake word | no | maybe | yes (Vosk AAR) | yes |
| Media/dark/lock | no | JNI pain | yes | yes |
| Store-ready | no | yes | yes | yes |
| Recommended | optional | no | yes, for reuse | yes, for product |
