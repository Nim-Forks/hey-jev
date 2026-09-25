# YodaOS / Rokid Glasses as a hey-jev target — research

Status: **research only, nothing implemented.** Researched 2026-09 from the
public YodaOS/AIUI repos and docs. Answer: **yes as a JavaScript AIUI agent,
with real caveats — and it's not the YodaOS you'll find on GitHub.**

## 1. Disambiguation: two unrelated things called YodaOS

| | YodaOS (classic) | AIUI (current) |
| --- | --- | --- |
| What | OpenWrt-based Linux distro for voice speakers; JS app framework (ShadowNode, yoda.js) | Agentic runtime **on Rokid Glasses** (RokidGlasses1/2, monochrome green display); JS/TS "agent" apps with Web-standard APIs |
| Hardware | Kamino18, Amlogic A113 speakers, Raspberry Pi 3B+ | Rokid AI glasses |
| State | Dormant (yoda.js 2023, ShadowNode 2024) | **Active** (commits through 2026-09), official tooling |
| Relevance | Wrong platform (speakers, no display interaction) | **The actual target** |

The open-source `yodaos-project/yodaos` repo is a dead end for glasses. The
glasses platform is **AIUI** (`yodaos-project/AIUI`, Apache-2.0), apps
packaged via the `aix` format (Rust), deployed through AIUI Studio / Craft.

## 2. What AIUI gives an app (verified from the API docs)

| hey-jev needs | AIUI API | Notes |
| --- | --- | --- |
| Speech → text | `SpeechRecognition` / `SpeechRecognitionSession` | Web Speech-style; **cloud ASR**, streaming or blob input, VAD segmentation (configurable silence — the desktop's 0.8s rule exists natively), phrase boosting, context updates; raw PCM 16 kHz mono s16/f32 |
| Reply → speech | `speechSynthesis.speak()`/`synthesize()` + `SpeechAudioPlayer` | built-in voices, word subtitles, streaming; **no `lang` switch/`getVoices()` yet** |
| LLM | `LanguageModel` (`availability()`, `create()`, `session.prompt()`) | built-in — could replace the OpenRouter fallback |
| HTTP | `fetch` | the brain's only external dependency works |
| Mic | `getUserMedia` + `MediaRecorder` | `RECORD_AUDIO` in app.json |
| Storage | `storage` APIs | sha1 wav-cache pattern ports |
| UI | `.ink` SFC pages, monochrome-green design system | status dot/timers feasible |
| Trigger | touch/temple press | interaction required — see wake word |

Scaffolding: `npm create @yodaos-pkg/aiui-agent@latest`; official `aiui-dev`
LLM skill exists for AI coding assistants.

## 3. The brain port

`jev()` → `fetch` POST with the same `QUESTIONS` JSON; `decide()`/
`split_actions()` → direct JS ports; gate 0.65 moves as-is; timers → JS
timers + regexes; `REPLIES` verbatim (strip Fish emotion tags if using
platform TTS); `ask_llm` → OpenRouter via fetch or built-in `LanguageModel`.

## 4. The voice conflict

1. **Platform TTS** — first-class, but a Rokid voice; loses Fish + tags.
2. **Fish over network** — fetch Fish wavs (same cache pattern), play via
   media APIs. Keeps her voice; costs round-trips (the warm cache already
   solves this). Recommended: Fish cache primary, platform TTS fallback.

## 5. What you do NOT get

- **No custom wake word** — recognition must start from a user interaction
  (docs say explicitly). Temple-press PTT only.
- **No PC control** — nothing to open/volume/dark-mode/lock; conversational
  half only (timers, reminders, questions, chit-chat).
- **Hardware risk**: low — ASR/TTS/LLM are cloud-side, on-device work is
  orchestration only (the two Android blockers don't exist here).

## 6. Verdict

| Target | Wake word | Fish voice | PC control | Effort | Verdict |
| --- | --- | --- | --- | --- | --- |
| Windows native | Alt PTT (+wake) | yes | **full** | done | best product |
| Android | PTT / native Vosk | yes | no | days–weeks | companion |
| **Rokid (AIUI)** | temple-press only | yes (cache) or TTS | no | **days** | best hands-free *companion* |

**Bottom line:** most natural home for the conversational brain, but a new
product surface, not a port of the Windows assistant.

## 7. Sketch (not implemented)

```
rokid-aiui/
  app.json        # permissions: ["RECORD_AUDIO"]
  app.js          # lifecycle: temple-press → startRecognition
  brain.js        # QUESTIONS + jev() (fetch) + decide() — ported
  timers.js       # parse_duration/run_timer + .ink rows
  voice.js        # Fish fetch_tts cache; speechSynthesis fallback
  pages/index.ink # status dot, states, timer list
```

Open questions: can media play a fetched wav buffer? ASR streaming fast
enough? temple-press events while another agent is foreground? Fish API
reachability from the glasses network stack?
