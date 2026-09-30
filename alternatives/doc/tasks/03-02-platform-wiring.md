# Task 3.2 — Integration: wire both platforms

**Spec**: tts-alternatives
**Branch**: `feature-alternatives`
**Status**: draft

---

## Task Overview

**Objective**: Give the win11 and linux platform layers their two persona path overrides and the startup-validation call — voice path and remote path — plus the one-conditional change that stops demanding a Fish key when the local backend is selected, so a machine without any cloud voice credentials can run entirely on the local backend.

**Dependencies**: Task 2.6 (`validate_startup`; this task is its wiring).

**Boundary**: platform startup only (both `siri.py` entry points). No platform-specific TTS/persona logic anywhere.

**Requirements**: 1.2, 1.3, 3.3, 5.2

## Implementation Steps

### Step 1: Persona storage path overrides
- [ ] Add the two path overrides beside the existing timers/cache overrides in each platform module: persona clip cache and persona state file, pointing into the platform's own folder (same pattern, platform-local state).
- **Observable**: each platform's persona state lands next to its `timers.json`, not in `shared/`.

### Step 2: Startup validation on the voice path
- [ ] After the existing decision-backend check (and before `--text`/voice execution): collect the TTS problems and exit with them joined by newlines if any.
- [ ] Make the Fish-key check conditional on the cloud backend: with the local backend selected, a missing Fish key is no longer fatal (name the alternative in the message); with the cloud backend, today's behavior is unchanged.
- **Observable**: with the local backend and no Fish key, the app starts; with the cloud backend and no key, today's exact message (extended hint); every invalid TTS combination exits before the mic with its named fix.

### Step 3: Startup validation on the remote path
- [ ] Insert the same validation before handing off to the remote runner — this is new for the remote path (it currently returns before even the Fish-key check, but the server process renders speech and must validate its configuration).
- [ ] Do NOT add the Fish-key check to the remote path: server-key semantics for the cloud backend are unchanged (the server's own key fallback logic stays as-is).
- **Observable**: `--remote` with an invalid local-backend configuration exits with the named fix before the server starts; a valid local-backend configuration starts the server.

### Step 4: Manual platform matrix
- [ ] On each platform, run the documented matrix: local backend + no Fish key (starts), local backend + engine missing (exits with install hint), local backend + non-en languages (exits with gate message), local backend + bad clip path (exits naming the file), unknown backend (exits naming valid values), cloud backend + no Fish key (exits with today's message), valid cloud backend (starts unchanged), `--remote` with each of the above.
- **Observable**: the matrix passes on win11 and linux; results recorded in the task's PR description.

## Files to Create/Modify

| File | Action | Purpose |
|------|--------|---------|
| `win11/siri.py` | Modify | Path overrides; conditional Fish-key check; validation on voice + remote paths |
| `linux/siri.py` | Modify | Same changes, linux file |

### File: `win11/siri.py` (and identically `linux/siri.py` at its own line numbers)

**Current Code** (win11 lines 19–20; linux lines 21–22 — the platform path overrides):

```python
config.TIMERS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "timers.json")
config.CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache", "tts")
```

**Expected Code After Implementation** (two lines appended):

```python
config.TIMERS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "timers.json")
config.CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache", "tts")
config.PERSONAS_CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache", "personas")
config.PERSONA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "persona.json")
```

**Current Code** (win11 `main()` lines 488–496; linux lines 437–445):

```python
    if args.remote:
        import remote
        remote.run_remote()
        return
    if not config.FISH_KEY:
        sys.exit("need FISH_AUDIO_API_KEY in Credential Manager or .env")
    if config.decision_backend() is None:
        sys.exit("need a decision backend in Credential Manager or .env: "
                 "TYPESAFE_API_KEY, or KEV_URL + KEV_API_KEY, or OPENROUTER_API_KEY")
```

**Expected Code After Implementation**:

```python
    if args.remote:
        problems = tts.validate_startup()
        if problems:
            sys.exit("\n".join(problems))
        import remote
        remote.run_remote()
        return
    if config.TTS_BACKEND == "fish" and not config.FISH_KEY:
        sys.exit("need FISH_AUDIO_API_KEY in Credential Manager or .env "
                 "(or set TTS_BACKEND=chatterbox for the local voice)")
    if config.decision_backend() is None:
        sys.exit("need a decision backend in Credential Manager or .env: "
                 "TYPESAFE_API_KEY, or KEV_URL + KEV_API_KEY, or OPENROUTER_API_KEY")
    problems = tts.validate_startup()
    if problems:
        sys.exit("\n".join(problems))
```

(plus `from shared import tts` added beside the file's existing shared imports — match the file's current import style.)

## Testing Approach

### Unit Tests
None — platform entry points are not unit-tested today (they import audio/OS modules at module scope); validation logic itself is covered by Task 2.6's suite.

### Manual Verification (the platform matrix)
1. `python siri.py --text "hello"` with `TTS_BACKEND=chatterbox`, no Fish key, engine installed → turn runs, wav cached
2. Same with the engine not installed → exits with the `requirements-tts-local` hint
3. Same with `WHISPER_LANGUAGES=en,de` → exits with the language-gate message
4. Same with `TTS_REF_CLIP=/no/such/clip.wav` → exits naming the file
5. `TTS_BACKEND=piper` → exits naming valid values
6. `TTS_BACKEND=fish` (default), no Fish key → exits with today's message + the chatterbox hint
7. `TTS_BACKEND=fish`, Fish key present → starts exactly as before the feature
8. `--remote` variants of 1–5 → same exits before the server starts; valid → server starts
   - Expected: identical behavior on win11 (PowerShell) and linux (shell); results recorded per platform

## Acceptance Criteria

- [ ] Persona state and clips live in each platform's own folder (never `shared/`)
- [ ] Every invalid TTS combination exits before the mic/server with its named fix, on both platforms
- [ ] Local backend starts without any Fish credential; cloud backend requires it exactly as today (message extended with the alternative)
- [ ] Remote path validates before the server starts; server-key cloud semantics unchanged
- [ ] No platform-specific TTS or persona logic; the diff is overrides + validation calls + one conditional
- [ ] All requirements covered: 1.2, 1.3, 3.3, 5.2

## Notes

- The Fish-key conditional is the one behavioral platform change beyond pure wiring — required by the feature's goal ("run without the cloud voice service"); flagged here so review doesn't mistake it for scope creep.
- `--ui` path: it launches the status window/assistant without passing through `main()`'s checks — same pre-existing gap as the Fish-key checks; left as-is (parity preserved), noted for a future consolidation.
- The linux service path (`deploy-service.sh` → `siri.py`/`remote.py` under systemd) inherits the same validation through `main()`/the remote wrapper — no service-file changes needed; multi-instance services each get their own persona state via the platform folder.
- Windows console encoding: `sys.exit("\n".join(...))` prints plain ASCII paths in practice; no special handling needed.
