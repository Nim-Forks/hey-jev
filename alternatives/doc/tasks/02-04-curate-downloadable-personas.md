# Task 2.4 — Curate the initial downloadable personas

**Spec**: tts-alternatives
**Branch**: `feature-alternatives`
**Status**: draft

---

## Task Overview

**Objective**: Add the two initial downloadable personas (one female, one male voice) to the catalog with exact, end-to-end-verified sources — the same screening criteria as the shipped default — so the persona switch works out of the box with three distinct voices.

**Dependencies**: Task 2.3 (the persona module its entries land in).

**Boundary**: `personas` component (catalog data + verification); no module logic changes.

**Requirements**: 10.1, 10.4

## Verified Candidates (2026-09-30)

Both verified today against the archive.org metadata endpoint (license field) and file listings (exact file names, sizes, durations):

| Field | Persona `kara` | Persona `kilmer` |
|---|---|---|
| Work | Poems Every Child Should Know (ed. Mary E. Burt) | Trees and Other Poems (Joyce Kilmer) |
| Reader (single) | Kara Shallenberg | Phil Chenevert |
| Voice | female, warm, clear | male, deep, unhurried |
| Item | `poems_every_child_should_know_librivox` | `treesandotherpoems_pc_librivox` |
| License (item) | `creativecommons.org/licenses/publicdomain/` | `creativecommons.org/publicdomain/zero/1.0/` (CC0) |
| Source file | `poems_every_child_31_burt_64kb.mp3` (3:30) | `treesandotherpoems_1_kilmer_64kb.mp3` (11:09) |
| Trim (initial) | start 60 s, 25 s | start 25 s, 25 s |

Screening checks already satisfied: permissive license in item metadata; single-reader recordings (description says "Read by …" with one name); per-recording direct 64kb file access; trim targets a natural mid-reading segment.

## Implementation Steps

### Step 1: Audible trim verification
- [ ] Download both source files once (they are the fetch targets; persona tests also fetch them via the module).
- [ ] Listen to the proposed trim windows and adjust `start_s` so the 25 s slice is mid-reading (no long silence, no mid-word start, no title announcement if one exists).
- **Observable**: both final clips are clean 25 s voice segments confirmed by ear.

### Step 2: Add the catalog entries
- [ ] Append the two entries (exact fields from the table above) to the catalog tuple; names lowercase, descriptions short and speakable ("a warm storytelling voice" / "a calm, deep narrator").
- [ ] Run the catalog construction — both entries pass the license screen (public domain + CC0 are both in the permissive set).
- **Observable**: `resolve("kara")` and `resolve("kilmer")` return canonical names; roster lists three personas.

### Step 3: End-to-end fetch through the persona module
- [ ] On a machine with network: call the module's clip lookup for both personas; assert each produces a 24 kHz mono wav in the persona cache; call again and confirm cache-only reuse.
- [ ] Re-run the wrong-license rejection case from Task 2.3's suite to prove the screen still fires (a CC-BY-NC-style entry must fail).
- [ ] Add the two real fetches as `@pytest.mark.slow @pytest.mark.network` tests (skipped cleanly offline), mirroring Task 2.2's real-model test shape.
- **Observable**: both personas fetch successfully through the module (24 kHz mono wav in the persona cache), second lookups do no network I/O, and the deliberate bad-license entry is rejected by the screen.

## Files to Create/Modify

| File | Action | Purpose |
|------|--------|---------|
| `shared/personas.py` | Modify | Append the two verified catalog entries |
| `shared/tests/test_personas.py` | Modify | Add the two real-fetch slow/network tests |
| `alternatives/doc/research.md` | Modify | Record the curation facts (items, files, licenses, trim ranges, verification date) |

### File: `shared/personas.py`

**Current Code** (the Task 2.3 catalog tuple):

```python
_PERSONAS = (
    {"name": "jev", "description": "the default Jev voice", "reader": "Elizabeth Klett",
     "source_url": None, "source_license": "publicdomain", "start_s": 0.0, "duration_s": 0.0},
    # two downloadable entries land in task 2.4 (same screening)
)
```

**Expected Code After Implementation**:

```python
_PERSONAS = (
    {"name": "jev", "description": "the default Jev voice", "reader": "Elizabeth Klett",
     "source_url": None, "source_license": "publicdomain", "start_s": 0.0, "duration_s": 0.0},
    {"name": "kara", "description": "a warm storytelling voice", "reader": "Kara Shallenberg",
     "source_url": "https://archive.org/download/poems_every_child_should_know_librivox/poems_every_child_31_burt_64kb.mp3",
     "source_license": "publicdomain", "start_s": 60.0, "duration_s": 25.0},
    {"name": "kilmer", "description": "a calm, deep narrator", "reader": "Phil Chenevert",
     "source_url": "https://archive.org/download/treesandotherpoems_pc_librivox/treesandotherpoems_1_kilmer_64kb.mp3",
     "source_license": "publicdomain", "start_s": 25.0, "duration_s": 25.0},
)
```

### File: `shared/tests/test_personas.py`

**Current Code**: the Task 2.3 suite (offline-stubbed).

**Expected Code After Implementation** (appended):

```python
REAL_PERSONAS = ("kara", "kilmer")


@pytest.mark.slow
@pytest.mark.network
@pytest.mark.parametrize("name", REAL_PERSONAS)
def test_real_personas_fetch_and_cache(name, state_isolation):
    p1 = personas.clip_for(name)
    assert p1 and p1.endswith(f"{name}.wav")
    data, sr = soundfile_read(p1)
    assert sr == personas.TARGET_SR and data.ndim == 1 and len(data) > sr * 20
    p2 = personas.clip_for(name)
    assert p1 == p2  # cache-only second call


def soundfile_read(path):
    import soundfile as sf
    return sf.read(path)
```

### File: `alternatives/doc/research.md`

**Current Code** (end of the persona-switch extension entry's Implications bullet):

```
- **Implications**: Personas become catalog entries (name → PD source + description) plus a per-persona clip cache; catalog curation and the fetch/screen flow belong to design.
```

**Expected Code After Implementation** (bullet extended):

```
- **Implications**: Personas become catalog entries (name → PD source + description) plus a per-persona clip cache; catalog curation and the fetch/screen flow belong to design.
- **Initial downloadable personas (curated 2026-09-30, verified against item metadata + file listings)**:
  `kara` — Poems Every Child Should Know, single reader Kara Shallenberg, item `poems_every_child_should_know_librivox`,
  file `poems_every_child_31_burt_64kb.mp3`, license publicdomain, trim 60 s + 25 s;
  `kilmer` — Trees and Other Poems, single reader Phil Chenevert, item `treesandotherpoems_pc_librivox`,
  file `treesandotherpoems_1_kilmer_64kb.mp3`, license CC0, trim 25 s + 25 s.
  Both verified end-to-end with the item metadata and file endpoints before cataloging.
```

## Testing Approach

### Unit Tests
Covered by Task 2.3's offline suite (screening, cache idempotency, persistence) — unchanged here.

### Slow / Network Tests
1. Real fetch per persona: 24 kHz mono wav ≥ 20 s in the persona cache; second lookup cache-only
   - Setup: network available, persona cache empty
   - Action: `clip_for("kara")`, `clip_for("kilmer")` twice
   - Expected: same cached path returned; no second download (Task 2.3's idempotency behavior)
2. Wrong-license rejection: CC-BY-NC entry still fails the screen
   - Expected: `RuntimeError` at construction (catalog) / `None` at fetch (metadata mismatch)

## Acceptance Criteria

- [ ] Both personas fetch successfully through the persona module and produce 24 kHz mono wavs in the persona cache
- [ ] A deliberately wrong license entry is rejected by the screen
- [ ] Catalog entries carry the exact file, trim range, reader, and license; trim windows verified by ear
- [ ] Offline re-fetch works after the first download (cache-only)
- [ ] All requirements covered: 10.1, 10.4

## Notes

- Persona names (`kara`, `kilmer`) are reader-derived and easy to say; Jev's routing (Task 2.5) enumerates exactly these names plus `jev`.
- Trim values are initial and audible-verified; they may shift ±10 s during Step 1 — the license and file fields must not change without re-running this task's verification.
- The 64kb derivative files are the fetch targets (small, stable, direct); the original VBR mp3s stay untouched as upstream sources.
- If a source file ever disappears (archive.org removal), `clip_for` returns `None` → the app keeps the current voice (Task 3.1 behavior); curation then replaces the entry via a new name or the same name after re-verification.
