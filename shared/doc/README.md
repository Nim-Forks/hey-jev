# shared/ — deduplicating the win11 and linux ports

Status: **proposal — waiting for approval. No code has been moved.**

## The problem

`win11/siri.py` (1,605 lines) and `linux/siri.py` (1,553 lines) are ~76%
identical line-for-line (1,218 exact-duplicate lines). The duplicated part
is the **brain** — the part that changes most often (routing, skills,
memory, timers, prompts, cost tracking). Every brain fix must currently be
applied twice and can silently drift.

Fully duplicated files (bit-identical today):

| File | Lines |
| --- | --- |
| `web/app.js` | 459 |
| `web/settings.html` | ~290 |
| `web/index.html` | ~110 |
| `web/worklet.js` | 34 |
| `secrets_store.py` | 42 |

Nearly identical (one small, intentional diff):
`remote.py` — 606 vs 609 lines; the **only** difference is the Linux
version's multilingual STT support (`whisper_spec()` + `_Whisper.get`
model-name switching, 13 diff lines).

`app.py` — trivial entry-point variants.

## The proposal

A `shared/` package at the repo root holds everything platform-neutral.
`win11/siri.py` and `linux/siri.py` shrink to thin platform layers
(~150-250 lines each: ACTIONS table, volume/mute/dark/lock/sleep helpers,
machine_context, chime, APPS, STT hooks) plus entry points.

Target layout:

```
shared/
  __init__.py
  config.py      # .env load, keys, backends, USE_KEV, GATE, JEV_MODEL,
                 # LLM_*, NTFY_URL, ALERT_MESSAGE, reload_keys(),
                 # decision_backend(), jev() — all globals live here as
                 # module attributes (see invariants)
  brain.py       # QUESTIONS, split_questions, decide/pick_action/
                 # split_actions, handle(), say/say_line/REPLIES, cancel
                 # (TurnCancelled, request_cancel, _cancel_check),
                 # LAST_TURN_COST, timers (add_timer, run_timer,
                 # start_timer_loop, timer_snapshot, timer_done_line,
                 # save/load, TIMERS), memory (fact/override/forget,
                 # MEMORY_SINK/CURRENT), skills (weather, sunrise,
                 # currency, wiki, joke, news, skill_line), LLM
                 # (ask_llm, machine-context hook), cost
  stt.py         # Recorder, pick_input(param), _Whisper loader,
                 # whisper spec via platform hook
  remote_server.py  # today's remote.py — parametrised STT hook
  web/           # app.js, index.html, settings.html, worklet.js
doc/             # this folder
```

Platform folders keep:

```
win11/
  siri.py        # from shared: `import shared.brain as brain`, defines
                 # ACTIONS (PowerShell/WASAPI/...), machine_context(),
                 # chime(), APPS, press_media, whisper_spec() → ("small.en", "en"),
                 # run_voice_assistant(), main()
  remote.py      # thin: wires shared.remote_server with the win11 STT hook
  deploy-service scripts, requirements, .env.example
linux/           # same shape: pactl/playerctl/gsettings layer,
                 # whisper_spec() → multilingual switch
```

## Import strategy

Platform entries add the repo root to `sys.path` (one line — both folders
are siblings):

```python
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared import brain, config
```

No packaging/pip changes; venvs already contain the deps.

## The one invariant that shapes the design

`remote.py` and tests patch **module globals** on `siri` (begin_turn sets
`siri.TS_KEY`/`siri.FISH_KEY`/…; `_execute_turn` swaps `siri.say`, sets
`siri.MEMORY_SINK`/`MEMORY_CURRENT`/`TURN_CANCEL`). In the shared design the
same contract moves to `shared.config` / `shared.brain` attributes:

- `begin_turn` patches `config.TS_KEY` … `config.LLM_MODEL` (+ restores)
- `_execute_turn` swaps `brain.say`, sets `brain.MEMORY_SINK` …
- `handle()` reads everything from `config`/`brain` — no local copies
  (the two past bugs — a stale `memory=MEMORY_CURRENT` and the
  `say`-patch-in-wrong-module — came from breaking exactly this rule)

Documented as a hard rule: **`handle()` must reference every overridable
value as `config.X` / `brain.X`, never as a local or a default-arg copy.**

## Migration plan (per approval, on `feature-shared`)

1. `shared/config.py` + `shared/brain.py` created as literal moves from
   `win11/siri.py` (the richer copy); platform globals (PTT_KEY, ACTIONS,
   machine_context, chime, APPS, press_media) stay behind in `win11/siri.py`
2. `win11/siri.py` rewritten as the thin layer; `remote.py` → thin wrapper
3. Verify: `--text` turn, `--remote` + web page turn, quota, cancel,
   memory, skills — full parity checklist
4. `linux/` migrated the same way (its `whisper_spec()` hook kept)
5. `deploy-service.sh` path check, systemd restart, Linux-box live test
6. Merge to `develop` → your verification → `release`

## Risks / notes

- **Global-patch contract** — see above; the one rule that must not drift.
- **Rollout order** — win11 first (it's the live box), linux second; between
  3 and 5 the two platforms temporarily diverge in structure (fine —
  `release`/`develop` already hold the working copies).
- **`app.py`/tray** — win11 tray (pystray) and linux X11 tkinter stay in
  their platform folders untouched.
- **Tests that stub `siri.handle`/`siri.jev`** — they'd stub
  `shared.brain.handle` after the refactor; noted in each doc section.
- **Rollback** — the refactor is a pure move; revert to `de9ef42`/`72e05d7`
  restores both ports exactly.
- **web/ files** — served from `shared/web` by the shared server; identical
  today, no forking reason.

## What stays duplicated (on purpose)

- Platform `ACTIONS` tables and helpers (osascript-vs-pactl is the point)
- `machine_context()` (WMI vs /proc)
- deploy/service files, requirements (win11: pynput/pystray; linux: not)
- platform `siri.py` entry points and `whisper_spec()` hooks

## Effort estimate

~2-3 focused sessions: move + thin out (mechanical), then parity retests on
both boxes. Net effect: brain/remote/web maintained once; win11/linux diffs
shrink to ~10:1 platform-only.
