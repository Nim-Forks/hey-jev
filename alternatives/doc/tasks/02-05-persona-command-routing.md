# Task 2.5 — Persona command routing in the turn flow

**Spec**: tts-alternatives
**Branch**: `feature-alternatives`
**Status**: draft

---

## Task Overview

**Objective**: Make "switch persona to X", "list personas" and friends first-class turn outcomes: two new fan-out questions with a deterministic phrasing override first (mirroring the memory override pattern), a `persona` decision kind, the handler that switches/lists/refuses, and the scripted reply lines — so a spoken or typed command resolves identically and unknown/cloud cases never touch the voice.

**Dependencies**: Tasks 2.1 (backend switch readable for the cloud refusal), 2.3 (persona resolve/roster/persistence).

**Boundary**: `brain routing` component (`brain.py`: questions, override, decide, handle, replies) + its tests. No TTS logic (the voice hookup of the switched persona is Task 3.1), no persona module changes.

**Requirements**: 9.1, 9.3, 9.4, 9.7

## Implementation Steps

### Step 1: Fan-out questions
- [ ] Add `persona_action` (choice: `switch` / `list` / `none`) and `persona_name` (choice: one criterion per catalog persona name + `none`, descriptions from the roster) to the question set, placed beside the memory questions.
- [ ] Add both to the global-question exclusion list so compound splitting never duplicates them (same list that already excludes category/compound/timer-ish globals).
- **Observable**: the fan-out question payload includes both questions; the split payload never contains `first_persona_action` / `second_persona_*` keys.

### Step 2: Deterministic override (regex first, Jev second)
- [ ] Add `persona_override(text)` mirroring `memory_override`: switch phrasings ("switch/change the persona to X", "switch to the X persona") capture the name; roster phrasings ("what/which/list … personas", "what persona are you") return list; non-matching text returns `None`.
- [ ] In `decide()`, check the persona override right after the memory override (before weather/skill/category branches); when the regex misses, read `persona_action` at the confidence gate — a confident `switch` with a confident name becomes `("switch", name)`, a confident `switch` without a confident name becomes `("switch", None)` (treated as unknown), a confident `list` becomes `("list", None)`.
- [ ] Return `("persona", (action, name))` from `decide()`.
- **Observable**: "switch persona to kilmer" resolves via the regex even when the decision backend answers noisily; a Jev-only phrasing resolves via the questions at the gate.

### Step 3: Handler branch
- [ ] Add the `persona` branch in the turn handler, mirroring the memory branch shape:
  - `list` → roster line (active persona flagged, available ones named).
  - `switch` with a known name on the **local** backend → persist the persona (module call) and speak the switched line (voice hookup = Task 3.1).
  - `switch` with an **unknown** name → keep the current voice, speak the roster line (9.3).
  - `switch` on the **cloud** backend → keep the voice, speak the needs-local line (9.7).
- **Observable**: each branch is covered by routing tests with a stubbed decision backend; no branch changes the voice on failure paths.

### Step 4: Scripted reply lines
- [ ] Add the persona reply entries beside the existing memory entries (tag-marked like every reply): switched line with a `{name}` placeholder, roster line, unknown line, needs-local line, unavailable line (fetch-failure wording — spoken by Task 3.1's flow, defined now so warm cache covers it).
- **Observable**: warm-up pre-renders the new lines automatically (they flow through the existing all-lines iterator) and the unit tests build them via the same say-line helper.

## Files to Create/Modify

| File | Action | Purpose |
|------|--------|---------|
| `shared/brain.py` | Modify | Questions, override regexes, decide branch, handle branch, reply lines |
| `shared/tests/test_routing.py` | Create | Regex vs Jev precedence, gate behavior, all handler branches with stubbed decision backend |

### File: `shared/brain.py` — questions

**Current Code** (lines 72–77 and 85–86):

```python
    "memory_action": {"type": "choice", "instructions": "Is the user asking the assistant to remember, recall or forget personal facts?",
                      "criteria": {"save": "asks to remember or store something for later ('remember that…')",
                                   "recall": "asks what was remembered or asks for a previously stored fact",
                                   "forget": "asks to forget something",
                                   "none": "not about stored memories"}},
}
```

```python
            if k in ("category", "compound", "needs_time", "needs_machine", "weather_action",
                     "info_skill", "memory_action"):
                continue
```

**Expected Code After Implementation** (entries appended inside `QUESTIONS` before the closing brace; exclusion list extended):

```python
    "persona_action": {"type": "choice", "instructions": "Is the user asking to switch the assistant's persona (voice character) or asking which personas exist?",
                       "criteria": {"switch": "asks to switch or change the assistant's persona to another one",
                                    "list": "asks which personas exist or which persona is currently active",
                                    "none": "not about personas at all"}},
    "persona_name": {"type": "choice", "instructions": "Which persona is named, if any?",
                     # criteria built from the persona catalog at import: names -> descriptions, plus "none"
                     **{p["name"]: p["description"] for p in _persona_catalog()},
                     **{"none": None}},
}
```

```python
            if k in ("category", "compound", "needs_time", "needs_machine", "weather_action",
                     "info_skill", "memory_action", "persona_action", "persona_name"):
                continue
```

(`_persona_catalog()` is a tiny helper importing the persona module's catalog lazily at import time — the catalog is code-defined, so the criteria are static; a `none` criterion is appended.)

### File: `shared/brain.py` — override + decide

**Current Code** (lines 126–135 of `decide()`):

```python
    op = memory_override(text) if text else None
    if op is None:
        mact, mconf = ans["memory_action"]
        if mact == "forget" and mconf >= 0.5:
            op = "forget"
    if op in ("save", "forget"):
        return ("memory", op)
    if op == "recall":
        return ("llm", None)  # memory rides the LLM context automatically
```

**Expected Code After Implementation** (persona block inserted directly after the memory block):

```python
    pop = persona_override(text) if text else None
    if pop is None:
        pact, pconf = ans["persona_action"]
        if pact == "switch" and pconf >= config.GATE:
            pname, pnconf = ans["persona_name"]
            pop = ("switch", pname if pnconf >= config.GATE else None)
        elif pact == "list" and pconf >= 0.5:
            pop = ("list", None)
    if pop:
        return ("persona", pop)
```

(new module-level regexes + `persona_override`, same shape as `memory_override`:)

```python
PERSONA_SWITCH_RE = re.compile(r"\b(?:switch|change|go)\s+(?:the\s+)?persona\s+(?:to|as)\s+([a-z]+)", re.I)
PERSONA_SWITCH_B_RE = re.compile(r"\bswitch\s+to\s+(?:the\s+)?([a-z]+)\s+persona\b", re.I)
PERSONA_LIST_RE = re.compile(r"\b(?:what|which|list)\b.*\bpersonas?\b|\bwhat\s+persona\s+are\s+you\b", re.I)


def persona_override(text):
    """Deterministic persona phrasing — exact name capture must not depend on
    the decision backend (same rationale as memory_override)."""
    t = (text or "").strip()
    if PERSONA_LIST_RE.search(t):
        return ("list", None)
    m = PERSONA_SWITCH_RE.search(t) or PERSONA_SWITCH_B_RE.search(t)
    if m:
        return ("switch", m.group(1).lower())
    return None
```

### File: `shared/brain.py` — handler branch

**Current Code** (lines 972–986 of `handle()`):

```python
        elif kind == "memory":
            op = payload
            sink = MEMORY_SINK
            if sink is None:
                line = say_line("memory_unsupported")
            elif op == "save":
                fact = memory_fact(text)
                if not fact:
                    line = say_line("memory_unclear")
                else:
                    sink("save", fact)
                    line = say_line("memory_saved")
            else:  # forget
                sink("forget", memory_forget(text))
                line = say_line("memory_forgot")
```

**Expected Code After Implementation** (persona branch inserted after the memory branch):

```python
        elif kind == "persona":
            action, name = payload
            if action == "list":
                line = say_line("persona_list",
                                current=personas.active(),
                                names=", ".join(p["name"] for p in personas.list_personas()))
            elif config.TTS_BACKEND != "chatterbox":
                line = say_line("persona_needs_local")          # 9.7: keep voice
            elif personas.resolve(name or "") is None:
                line = say_line("persona_unknown", names=", ".join(p["name"] for p in personas.list_personas()))
            elif personas.clip_for(name) is None:
                line = say_line("persona_unavailable")          # 10.5 wording; keeps voice
            else:
                personas.set_active(name)
                line = say_line("persona_switched", name=name)  # voice hookup: task 3.1
```

### File: `shared/brain.py` — reply lines

**Current Code**: the `REPLIES` dict's `memory_*` entries (add adjacent).

**Expected Code After Implementation** (appended to `REPLIES`):

```python
    "persona_switched": ["[cheerful] Persona switched to {name}. I sound a little different now."],
    "persona_list": ["My personas: {names}. Right now I am {current}."],
    "persona_unknown": ["I don't know that one. I can be: {names}."],
    "persona_needs_local": ["Persona switching works with my local voice. That needs the local speech backend."],
    "persona_unavailable": ["I couldn't fetch that persona's voice right now, so I'll stay as I am."],
```

### File: `shared/tests/test_routing.py`

**Current Code**: none.

**Expected Code** (essentials):

```python
import pytest

from shared import brain, config, personas


def base_ans(**over):
    a = {"category": ("chit_chat", 0.9), "compound": (False, 0.9), "target": ("none", 0.2),
         "weather_action": ("none", 0.9), "info_skill": ("none", 0.9),
         "memory_action": ("none", 0.9), "persona_action": ("none", 0.2),
         "persona_name": ("none", 0.2)}
    a.update(over)
    return a


def test_regex_wins_over_noisy_jev():
    kind, payload = brain.decide(base_ans(), "hey jev, switch persona to Kilmer")
    assert (kind, payload) == ("persona", ("switch", "kilmer"))


def test_jev_fallback_switch_with_name():
    ans = base_ans(persona_action=("switch", 0.9), persona_name=("kara", 0.9))
    assert brain.decide(ans, "i'd like a different voice") == ("persona", ("switch", "kara"))


def test_jev_switch_without_confident_name_is_unknown():
    ans = base_ans(persona_action=("switch", 0.9), persona_name=("none", 0.3))
    assert brain.decide(ans, "give me another voice") == ("persona", ("switch", None))


def test_list_phrasing():
    assert brain.decide(base_ans(), "what personas are there?") == ("persona", ("list", None))


def test_unknown_switch_keeps_voice_and_lists(state_isolation):
    line = brain._persona_reply(("switch", "bogus"))
    assert "kara" in line and "kilmer" in line
    assert personas.active() == "jev"          # voice untouched


def test_cloud_backend_refuses(state_isolation, monkeypatch):
    monkeypatch.setattr(config, "TTS_BACKEND", "fish")
    line = brain._persona_reply(("switch", "kara"))
    assert "local" in line
    assert personas.active() == "jev"


def test_switch_persists(state_isolation):
    line = brain._persona_reply(("switch", "kara"))
    assert "kara" in line
    assert personas.active() == "kara"          # full voice swap: task 3.1
```

(Extract the branch body into a small `persona_line`-style helper so tests drive it without running a full turn; the handler branch then stays a thin call — final helper name at implementation, keeping one code path.)

## Testing Approach

### Unit Tests (offline, decision backend stubbed)
1. Regex precedence: noisy/garbage Jev answers cannot derail an exact switch phrase (9.1)
2. Jev fallback: action at gate + confident name → switch; name below gate → unknown path (9.3)
3. List phrasing → roster decision (9.4)
4. Handler branches: unknown keeps voice and names the roster; cloud backend refuses with explanation; successful switch persists the persona (9.1, 9.3, 9.7)
5. Exclusion: split payload contains no persona keys

### Integration Tests
Full switch-with-voice and fetch-failure flows land in Tasks 3.1/4.2.

## Acceptance Criteria

- [ ] Spoken and typed switch phrasings resolve to the same decision via regex; Jev covers phrasings the regex misses at the normal gate
- [ ] Unknown persona keeps the current voice and names the available ones; roster phrasing announces active + available
- [ ] Cloud backend keeps the voice and explains the local-backend requirement
- [ ] Successful switch persists the persona (state file) and confirms; the spoken confirmation in the new voice is Task 3.1
- [ ] Persona questions never appear in compound split payloads
- [ ] All requirements covered: 9.1, 9.3, 9.4, 9.7

## Notes

- Regex order matters: the roster regex runs before the switch regexes; the switch regexes require an explicit persona word, so ordinary chat never trips them.
- The cloud-backend check comes before resolution on purpose: on `fish` we don't even look up the persona (one less surprise, same reply for any name).
- `persona_name` criteria are built at import from the code-defined catalog; adding a persona in Task 2.4 automatically extends the fan-out (no question edits needed).
- The switched line's `{name}` uses the canonical (lowercase) persona name; spoken niceties stay in the reply text.
