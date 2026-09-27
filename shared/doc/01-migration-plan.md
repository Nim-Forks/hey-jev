# Migration plan — module-by-module map

Every symbol from today's `win11/siri.py` and where it lands. The linux
copy is byte-equal except the platform deltas, so this map covers both.

## 1. `shared/config.py` (from win11/siri.py top + decision_backend)

Moves as-is:

- `.env` loading, `TS_KEY`, `FISH_KEY`, `OR_KEY`, `KEV_URL`, `KEV_KEY`,
  `USE_KEV`, `GATE` (JEV_GATE logic), `JEV_MODEL`, `WHISPER_MODEL`,
  `LLM_MODEL`, `LLM_MAX_TOKENS`, `NTFY_URL`, `ALERT_MESSAGE`,
  `VOICE_ID`, `SAMPLE_RATE`, `COMMAND_PROMPT`, `WAKE_PROMPT`, `WAKE`,
  `WAKE_WINDOW`, `REPLIES-adjacent constants`
- `reload_keys()`
- `decision_backend()`, `jev(text, questions)` (incl. cost + backend print)
- `SERVER_KEY_LIMIT` (read by remote; move here or to remote_server — pick
  config.py for one home)

Note: `PTT_KEY = keyboard.Key.alt_r if keyboard is not None else None`
(linux guard) → stays in the platform layer; win keeps its unconditional
form.

## 2. `shared/brain.py` (the bulk)

- `QUESTIONS`, `split_questions()`, `SPLIT_QUESTIONS`
- `sub_action()`, `decide(ans, text)`, `pick_action()`, `split_actions()`
- `REPLIES`, `say_line()`, `TARGETS`, `SPEAK_FIRST`
- timers: `NUMBER_WORDS`, `UNITS`, `DURATION`, `_digits`, `parse_duration`,
  `parse_reminder`, `say_duration`, `TIMERS`/`TIMERS_LOCK` (RLock),
  `add_timer`, `prepare_reminder`, `timer_snapshot`, `short_duration`,
  `run_timer`, `start_timer_loop`, `timer_done_line`, `save_timers`,
  `load_timers`, `TIMERS_FILE`, `next_alarm_end`, `add_alarm`
- LLM: `ask_llm(text, need_time, need_machine, memory)`,
  `ask_llm_with_memory` shim (if still referenced)
- machine-context **hook**: `ask_llm` currently calls `machine_context()`
  directly → becomes `config.machine_context_hook()` set by the platform
  (win: WMI/PS version; linux: /proc version)
- skills: `WEATHER_PLACE`, `CONDITION`, `IN_PLACE`, `extract_place`,
  `_hour_label`, `weather_line`, `SUN_KW`, `_geocode`, `_to24`,
  `sunrise_line`, `CURRENCY_*`, `currency_line`, `wiki_topic`, `wiki_line`,
  `joke_line`, `news_line`, `skill_line`
- memory: `MEMORY_SINK`, `MEMORY_CURRENT`, `memory_fact`, `MEM_*_RE`,
  `memory_override`, `memory_forget`
- one-turn: `misses`, `LAST_TURN_COST`, `TURN_CANCEL`, `TurnCancelled`,
  `request_cancel`, `_cancel_check`, `emit`, `handle(text, stt_ms, notify)`,
  `say(line, notify)`
- `fetch_tts`, `play_wav_path` **hook**: `speak()` currently calls
  `play_wav` (platform sounddevice) → same hook treatment as
  machine_context (`config.play_wav_hook`)
- `warm_cache`, `all_scripted_lines`

Hook contract (set once at platform import, before any turn):

```python
config.machine_context_hook = machine_context   # platform fn
config.play_wav_hook = play_wav                 # platform fn
```

## 3. `shared/stt.py`

- `Recorder` class (uses numpy/queue only)
- `pick_input()` — parametrised: `pick_input(skip_monitor=False)` (linux
  passes True)
- `_Whisper` loader — takes `(model_name)` (linux version superset)
- `transcribe_text(audio, notify, prompt)` — uses the **STT spec hook**

STT spec hook (platform-supplied): `config.stt_spec() -> (model, language)`
— win11 **gains multilingual support from `shared/`**: once the platform
layer provides the hook, the linux `whisper_spec()` logic (WHISPER_LANGUAGES
env → multilingual `small` model when cached + language auto-detect, en-only
fallback to `small.en`) moves into `shared/stt.py` and runs identically on
both platforms. Windows gets other-language voice input for free the moment
`WHISPER_LANGUAGES` is set in its `.env` and the multilingual model is
cached (`install.sh` on linux pre-downloads it; the win11 equivalent is one
huggingface snapshot — same helper).

## 4. `shared/remote_server.py`

Today's `remote.py` verbatim, with three substitutions:

- `import siri` → `from shared import brain, config`
- `_Whisper.get(notify)` → `_Whisper.get(notify, config.stt_spec())`
- everything else identical (quota, sessions, memory sink, ntfy,
  broadcast, tiles, weather-at, cancel, HTTP/WS plumbing)

## 5. Platform layers (what remains in win11/ and linux/)

| stays | reason |
| --- | --- |
| `ACTIONS` dict + helpers | osascript/PS vs pactl/playerctl |
| `machine_context()` | WMI vs /proc |
| `chime()` | winsound vs paplay |
| `APPS` table | launch commands + display names |
| `press_media` | pynput keys vs playerctl |
| `whisper_spec()` | one platform decides en-only vs multilingual — **or** (default plan) the spec logic itself lives in `shared/stt.py` reading `config.WHISPER_LANGUAGES`, so both platforms share it and win11 simply gains multilingual |
| `pick_input` param | monitor-skip policy |
| `run_voice_assistant()` | wake/PTT loop (keyboard guard on linux) |
| `main()` + `--remote` wrapper | argparse + STT hook wiring |
| `deploy-service.sh` / `.service` | user/paths |

## 6. Sequencing (after approval, on `feature-shared`)

1. Create `shared/` from win11 (mechanical move + hooks)
2. Rewrite `win11/siri.py` + `win11/remote.py` as thin layers
3. **Full parity checklist on Windows** (see below)
4. Commit → merge to `develop` → your verification
5. Port `linux/` to the thin layer, deploy to the Linux box, retest
6. Merge to `develop` → verify → `release`

Parity checklist (per platform): `--text` simple command; timer set + fire;
alarm; weather; rain verdict; sunrise; currency; wiki; joke; news;
memory save/recall/forget; typed web turn; voice web turn; cancel;
quota; token gate; tiles + location weather; history replay/re-run/edit.

## 7. File moves at a glance

| today | becomes |
| --- | --- |
| `win11/siri.py` 1,605 ln | `shared/config.py` (~120) + `shared/brain.py` (~950) + `win11/siri.py` (~250) |
| `linux/siri.py` 1,553 ln | (delta only) + `linux/siri.py` (~250) |
| `win11/remote.py` 606 ln | `shared/remote_server.py` (~600) + thin wrappers (~20) |
| `win11/web/*` 4 files | `shared/web/*` |
| `secrets_store.py` ×2 | `shared/secrets_store.py` |

## 8. Win11 multilingual — side effect of sharing

Today `win11` is en-only only because `whisper_spec()` lives in the linux
copy. Under `shared/`:

- `WHISPER_LANGUAGES` is read from `win11/.env` (same var, same installer
  prompt in a future win11 install.sh)
- `shared/stt.py` resolves the spec: non-en configured + multilingual model
  cached → `("small", None)` (auto-detect); else `("small.en", "en")`
- Model download on Windows is the same one-liner (huggingface snapshot of
  `Systran/faster-whisper-small` — ~470 MB, into
  `%USERPROFILE%\.cache\huggingface`)
- Verification on win11 after refactor: Fish-synthesize a phrase in one of
  the configured non-English languages, feed it as a web-remote voice turn,
  expect the transcript + reply in that language (same test used to verify
  the linux port)
