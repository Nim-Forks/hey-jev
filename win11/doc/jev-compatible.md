# Swapping the decision backend (Jev-compatible endpoints)

The app's decision backend is selected per call by `decision_backend()`
(priority **KEV > Typesafe > OpenRouter**). Any service that speaks the same
wire contract can replace Typesafe. This doc records the contract, what a
Jev-compatible alternative (referred to here as **KEV**) was verified to
support, and how the switching is implemented. No third-party service URL
is named in these docs on purpose.

## 1. The wire contract

Request — one POST per turn:

```
POST {base}/v1/systemone
Authorization: Bearer <key>
Content-Type: application/json

{
  "model":  "jev-latest",
  "state":  "<the transcript>",
  "questions": {
    "<name>": {"type": "choice", "instructions": "...", "criteria": {"label": "desc"|null, ...}},
    "<name>": {"type": "noul",   "instructions": "..."},
    "<name>": {"type": "score",  "instructions": "...", "criteria": ["step0", ...]}
  }
}
```

Response, as consumed:

| Field | Type | Used for |
| --- | --- | --- |
| `answers.<name>.type` | `"choice" \| "noul" \| "score"` | dispatch |
| `answers.<name>.noul` | float 0-1 | boolean; confidence = `max(p, 1-p)` client-side |
| `answers.<name>.choice` | string | selected label |
| `answers.<name>.score` | float | rounded to int, indexes the rubric |
| `answers.<name>.legend` | object, string int keys | **required** for score questions |
| `answers.<name>.confidence` | float (optional) | gated at 0.45/0.65 |
| `usage.input_tokens` / `usage.cost` | optional | cost display |

## 2. KEV — verified compatible

Probed via OpenAPI schema + live smoke test (all checks passed):

- `POST /v1/systemone` with Bearer auth; Typesafe-style request/response.
- `noul` without criteria, `choice` with null criteria values, `score` with
  array rubrics — all accepted.
- Response carries `answers` (with `legend` string keys), `usage`
  (`input_tokens`, `output_tokens`), extra keys (`model`, `latency_ms`)
  harmlessly ignored.
- `GET /v1/models` lists both `kev-latest` and `jev-latest` as aliases of
  the same card (a small CPU-served model at high temperature — expect
  lower confidences than Typesafe; the app auto-drops the gate to 0.45).
- Extras the app doesn't use (potential, later): `/v1/systemone/permute`
  (option-order debiasing), `/v1/systemone/separate`, model cards.

**Known quality caveat:** in testing, several correct answers landed below
0.65 (e.g. a correct `timer_action=set` at ~0.5) — mitigations: lower
temperature / bigger checkpoint, `permute`, or the auto-dropped gate.

## 3. Backend switching — implemented in the port

`decision_backend()` (in `win11/siri.py`) picks per call, priority
**KEV → Typesafe → OpenRouter**:

1. `KEV_URL` + `KEV_API_KEY` (both non-empty) → `{KEV_URL}/v1/systemone`,
   model `jev-latest` (aliased by KEV, verified live).
2. `TYPESAFE_API_KEY` → the Typesafe cloud.
3. Otherwise, if `OPENROUTER_API_KEY` is set → OpenRouter's decisions API
   (`https://openrouter.ai/api/alpha/decisions`, model `typesafe/jev-1.13`,
   `JEV_MODEL` override) — same wire contract, verified live end-to-end.

The cost line prefers `usage.cost` when a backend reports one, else the
Typesafe token formula. The gate is KEV-aware (`0.45` for KEV, `0.65`
otherwise, `JEV_GATE` override). Remote web clients can override
`KEV_URL`/`KEV_API_KEY`/`LLM_MODEL` per connection (localStorage keys) —
each device can run its own backend.

## 4. Smoke test with a real key (run before trusting a swap)

```bash
curl -sS -X POST "$JEV_BASE_URL/v1/systemone" \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"model":"'"$JEV_MODEL"'","state":"open spotify and turn it down","questions":{...}}'
```

Use the full `QUESTIONS` payload for `{...}`. Check: HTTP 200, `answers`
keyed by question name, `noul` floats, `score` + `legend` with string int
keys, `usage.input_tokens`. Repeat with a timer phrase and the
SPLIT_QUESTIONS payload shape.

**Status: executed against the KEV deployment (2026-09-24) and all points
passed.**

## 5. Compatibility checklist for any future backend

- [x] `POST {base}/v1/systemone`, bearer auth, JSON in/out *(KEV: pass)*
- [x] accepts `choice` with `criteria` values of `null` *(KEV: pass)*
- [x] accepts `noul` with no `criteria` *(KEV: pass)*
- [x] accepts `score` with array `criteria` *(KEV: pass)*
- [x] returns `answers` keyed by question name *(KEV: pass)*
- [x] `choice` → label string (+ optional `confidence`) *(KEV: pass)*
- [x] `noul` → float *(KEV: pass)*
- [x] `score` → float **and** `legend` with string int keys *(KEV: pass)*
- [x] optional `usage.input_tokens` (cost print only) *(KEV: pass)*
- [x] tolerates the app's model string or the operator sets an override *(KEV: pass)*
