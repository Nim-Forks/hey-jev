# Task 4.4 — Manual end-to-end gates on both platforms

**Spec**: tts-alternatives
**Branch**: `feature-alternatives`
**Status**: draft

---

## Task Overview

**Objective**: The human gate before merge: run the feature's user-visible behaviors on real win11 and linux machines — both backends, the local backend coexisting with decision/LLM traffic, a persona-voiced timer alert with emotion tags, the web remote turn, and a mid-turn cancel — and file anything that regresses.

**Dependencies**: Task 3.2 (platforms wired and starting). This task creates no code; the checklist below is the deliverable, results are recorded in the merge request.

**Boundary**: platform startup (win11, linux), tts, personas — observation only.

**Requirements**: 2.4, 6.1, 6.3, 7.2, 8.2

## Environment Preparation (per platform)

- Optional engine installed per `shared/requirements-tts-local.txt`, weights cached (one prior render).
- Both personas `kara` and `kilmer` fetched once (network available during prep; the gates themselves run offline except the LLM/decision traffic in Gate 2, which uses the configured backends).
- Start from a clean reply cache (`cache/tts` emptied) so first-render behavior is visible.

## Gate Checklist

### Gate 1 — One `--text` turn per backend (1.1, 1.2)
- [ ] `python siri.py --text "good morning"` with `TTS_BACKEND=fish` → cloud render, wav cached, reply plays through the platform hook.
- [ ] Same with `TTS_BACKEND=chatterbox` → local render, wav cached, reply plays; console trace shows `tts chatterbox`.
- **Expected**: both backends speak; the fish turn behaves exactly as before the feature; no visible latency difference beyond the first local render.

### Gate 2 — Decision/LLM traffic unaffected by the TTS setting (7.2, 8.2)
- [ ] With the local backend active, ask a live question by voice or `--text`: "what is the weather in berlin" (decision backend + weather fetch) and "who wrote the raven" (decision backend + LLM).
- [ ] Console shows the decision backend and LLM lines as usual; the spoken answers render locally.
- [ ] First uncached LLM answer: the turn shows Thinking then Speaking and the answer plays when ready — never dropped (8.2).
- **Expected**: the TTS setting changes nothing about where decisions/questions go; slow first renders still play.

### Gate 3 — Timer alert with the active persona and tag handling (2.4)
- [ ] Switch persona ("switch persona to kilmer"), then "set a timer for one minute" → confirmation in the new voice.
- [ ] Wait for the alert: chime + spoken alert line in kilmer's voice; **no bracket tags spoken aloud**; any emotion tag in the alert renders as expression (local backend: mapped/stripped per the tag table).
- [ ] "cancel my timer" and "cancel my reminders" behave as before.
- **Expected**: alert flow identical to today except the voice; tags never leak into speech.

### Gate 4 — Web remote turn and mid-turn cancel (existing flows preserved)
- [ ] `python siri.py --remote` with the local backend; browser connects (server key or client key as configured), hold-to-talk a request → streamed wav plays in the browser.
- [ ] Start a longer turn (LLM question) and cancel mid-turn (Stop) → turn aborts, state returns to Ready, the next turn works normally.
- **Expected**: remote protocol, quota, and cancel behavior unchanged; persona voice applies to remote turns too (server-side voice).

### Gate 5 — Failure resilience spot-check (6.1, 6.3)
- [ ] While running with the local backend, delete the active persona's cached clip file, then trigger a new spoken line → error is reported (status surface + console), the session stays usable, and the next turn succeeds (clip re-fetched or persona fallback per design).
- [ ] During a first-time model load (fresh weights cache), observe the status states — activity is shown, the window is never frozen.
- **Expected**: one bad render never ends the session; loading is visible activity, not a hang.

### Gate 6 — Persona persistence across restart (9.6, spot)
- [ ] With kilmer active, restart the app → greeting/speech still in kilmer's voice without any re-fetch.
- **Expected**: the persona state file drives the voice across restarts; no network call at startup for personas.

## Recording

- [ ] Fill the results table per platform (win11 / linux): each gate PASS/FAIL, notes, timings for Gate 2's first render.
- [ ] File regressions before merge; fix-forward or open follow-up tasks — the gate blocks merge while any regression is open.

## Files to Create/Modify

| File | Action | Purpose |
|------|--------|---------|
| *(none — checklist task; results recorded in the merge request)* | — | — |

## Testing Approach

### Manual Verification
The gates above are the test. Automation already covers: unit (tags/cache/personas/routing), offline integration (backends, warm cache, persona turns), and the RTF harness (8.1 evidence). This task covers only what automation cannot see: real audio output, real platform audio paths, real remote session, real cancel timing.

## Acceptance Criteria

- [ ] All six gates PASS on win11 and linux with the local backend selected
- [ ] Decision/LLM traffic demonstrably unaffected by the TTS setting (Gate 2 console evidence)
- [ ] Timer alert spoken with the active persona; no bracket tags audible (Gate 3)
- [ ] Remote turn + mid-turn cancel unchanged (Gate 4)
- [ ] Failure resilience and loading states observed (Gate 5); persona survives restart (Gate 6)
- [ ] All requirements covered: 2.4, 6.1, 6.3, 7.2, 8.2

## Notes

- Keep Gate 2's LLM answer non-trivial enough to exceed the reply cache (a fresh question), so 8.2's "plays when ready" is actually exercised.
- If the local engine is unavailable on a platform, Gates 1/2/3 run in fish mode and the local-only gates are marked N/A with the reason — the feature's default path must still pass.
- This checklist doubles as the release smoke test for future backend changes (revalidation trigger in the design's Boundary Commitments).
