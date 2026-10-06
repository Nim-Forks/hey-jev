# System One backends — self-hosted decision servers

Status: **deployed on the geekom 2026-10-04** (anarkali, von, opendecider,
laya self-hosted; kev and liquid proxied) · Source research:
`jev-mcp/doc/features/feature-alternatives/`.

## Why

Hosted KEV answers correctly but runs hot — measured 12–15 s per decision on
the combo instances (one 30 s timeout in 8 turns), at $0.000037/decision.
The System One family has CPU-viable drop-in servers that answer the same
`POST /v1/systemone` wire contract KEV uses — same envelope hey-jev already
speaks (`shared/config.py` posts `{model, state, questions}` and parses the
`{answers}` shape).

## The zero-code-change integration

`shared/config.py` treats any `KEV_URL + KEV_API_KEY` pair as a decision
backend and calls `f"{KEV_URL}/v1/systemone"`. Every candidate below speaks
that contract, so **any hey-jev instance can use any candidate today by
editing `.env` only**:

```env
KEV_URL=http://127.0.0.1:8901
KEV_API_KEY=whatever-the-server-expects   # many local servers accept any token
KEV_MODEL=d1:free                          # only for Liquid; omit for hosted KEV
```

Effects (already built into the chain):

- `USE_KEV=True` → the confidence gate drops to **0.45** (set `JEV_GATE=0.65`
  in the instance `.env` to keep the strict gate while evaluating).
- `KEV_MODEL` (`f8da21e`) overrides the model id the KEV branch sends —
  Liquid rejects `jev-latest`, so Liquid instances set `KEV_MODEL=d1:free`;
  everything else keeps the default.
- Logs show `backend: kev` — cosmetic mislabel until provenance work lands;
  the trace's URL tells the truth.
- Decision timeout stays 30 s — candidates answer in ms, so this only helps.
- `Liquid d1` is hosted with path `/decisions/v1/systemone` — set
  `KEV_URL=https://<vendor-host>/decisions` and the concatenation lands on
  the right path.

Verify per candidate **before trusting it on a public instance**: response
field parity (choice / score / noul + confidence vs the KEV parser) and an
agreement-rate run against hosted KEV on real turns (log both answers
side-by-side; promote on measured disagreement, not on author benchmarks).

## Candidate matrix — deployed

| candidate | runs as | port / URL (local) | warm decision (3-q fan-out) | auth env | notes |
|---|---|---|---|---|---|
| **anarkali** | `systemone-anarkali.service`, `anarkali serve --model toufiqqureshi651/anarkali --port 8901 --threads 4` (no `--host` flag — binds 0.0.0.0, key protects it) | `http://127.0.0.1:8901/v1/systemone` | **0.81 s** | `ANARKALI_API_KEY` | confidences low on the test fan-out — needs calibration evaluation |
| **von** | `systemone-von.service`, `von serve --host 127.0.0.1 --port 8902 --model latest` | `http://127.0.0.1:8902/v1/systemone` | **0.67 s** | `VON_API_KEY` | first request pays weight load (~10 min cold); strong confidences on test |
| **opendecider** | `systemone-opendecider.service`, `opendecider serve --model manjunathshiva/opendecider-nano --host 127.0.0.1 --port 8903` | `http://127.0.0.1:8903/v1/systemone` (+ `/ready`, `/metrics`) | **0.45 s** | `OPENDECIDER_API_KEY` | best measured speed; pins `>=0.2.1` |
| **laya** | `systemone-laya.service`, `laya-serve` (envs: `LAYA_PORT=8904 LAYA_MODELS=english LAYA_MAX_LOADED=1 LAYA_IDLE_UNLOAD_SECONDS=600`) | `http://127.0.0.1:8904/v1/systemone` | **0.46 s** | `LAYA_API_KEY` | lazy loads, unloads after 10 min idle — first hr request pays a reload |
| **clef** | nothing local — Workers AI `@cf/cloudflare/clef` via the **gate's cloud mode** | instance: `KEV_URL=http://127.0.0.1:8900/clef`, `KEV_MODEL=clef` | **0.6 s** on the real 15-q fan-out | `CLEF_KEY` (a Workers AI token, in `deciders.env`) | deterministic, image input, 65k context, ~$0.06/1k turns; envelope (`{"result": ...}`) unwrapped by the gate; Clef-flash is the faster/cheaper variant; `confidence` = distribution concentration, not the winner's probability |
| **kev** | nothing local — tunnel proxy `kev.nimes.in` → `https://kev.nimesin.online` | existing hosted KEV under the uniform name | 12–15 s (hosted) | existing KEV key | CPU self-host of Kev-0.8B is unsupported upstream; revisit later |
| **liquid d1** | nothing local — hosted `https://api.liquid.ai/decisions` | instance: `KEV_URL=https://api.liquid.ai/decisions` + `KEV_MODEL=d1:free` + own `liquid_` key | **0.9 s on the real 15-question fan-out** | own `liquid_` key (console.liquid.ai) | **live since 2026-10-04**: fastest of all backends, calibrated (0.995 on the timer probe), `d1:free` tier; needs `KEV_MODEL` (`f8da21e`) because Liquid rejects `jev-latest` |

All four self-hosted answer the packed multi-question call hey-jev sends
(~17 questions on a real turn → expect ~2–5 s per decision, still 3–5×
faster than hosted KEV). All share one bearer key =
prod's `KEV_API_KEY` value, written at deploy time to
`~/deciders/deciders.env` (root-private) and injected via
`EnvironmentFile` — hey-jev `.env` files need **only** a `KEV_URL` change.

Measured warm (3-question probe, geekom CPU): anarkali 0.81 s, von 0.67 s,
opendecider 0.45 s, laya 0.46 s — vs hosted KEV 12–15 s.

## Memory (measured 2026-10-04)

| process | resident RSS | note |
|---|---|---|
| anarkali | 473 MB | model resident |
| von | 2.1 GB | biggest; 3 GB weights on disk (`von/hf`) |
| opendecider | 1.5 GB | model resident |
| laya | 368 MB idle / ~1.7 GB loaded | own idle-unload (10 min) |
| systemone-gate | 54 MB | the on-demand supervisor |
| **all four resident** | **~4.4 GB** | pushed the 11 GiB box into swap |

Disk: per-venv 207 MB (anarkali, no torch) – 1.2 GB (torch-based ones);
weights 3 GB (von) / 808 MB (laya) / 759 MB (opendecider); anarkali ONNX
smallest.

## Dynamic gate — no resident RAM, no swap

`systemone-gate.service` (127.0.0.1:8900, 54 MB) owns the four deciders:

- The decider units are **disabled at boot and stopped**; the gate starts a
  unit on first request, waits for its port (120 s), retries 5xx/transport
  errors (covers lazy model loads), proxies the call, and **stops units with
  no traffic for `GATE_IDLE_STOP` seconds (default 600)** — verified with a
  20 s window.
- Routing: path prefix (`/<name>/v1/systemone`) **or** Host header — the
  public subdomains (`anarkali|von|opendecider|laya.nimes.in`) are re-pointed
  at the gate in the tunnel config, so both local and public names keep
  working.
- **Cloud mode**: credentials in `deciders.env` under `CLEF_URL`/`CLEF_KEY`
  register `clef` as a hosted backend — the gate forwards to the full Workers
  AI URL (model id lives in the URL, so hey-jev's `/v1/systemone` suffix is
  absorbed), unwraps the `{"success", "result"}` envelope, and accepts only
  the `CLEF_KEY` bearer for it. No janitor entry — the cloud backend has no
  local process to stop.
- hey-jev usage (any instance, `.env` only):
  `KEV_URL=http://127.0.0.1:8900/laya` — same bearer as before; gate 0.45
  applies.
- Cold-start through the gate (laya, stopped → answer): **4.0 s** total,
  warm 0.46 s. Caveat: von/opendecider reloads may exceed hey-jev's 30 s
  decision timeout on the very first call after a cold gate — the fix is
  regular use (idle window keeps the hot backend resident) or raising
  `GATE_IDLE_STOP`.
- Net effect: idle RAM for decisions ≈ **54 MB instead of ~4.4 GB** — no
  decider pages in swap; measured box state after idle-stop: 4.3 GB used,
  7.2 GB available.

## Stress results — full 15-question fan-out (2026-10-04)

The real `brain.QUESTIONS` packed call, 7 phrase groups × 3 variants
(21 calls per backend), agreement = expected routing labels
(target/category/timer_action/persona_action/volume_action) over 18 checks:

| backend | mean | p50 | max | agreement | wrong-but-conf-0.9 | errors |
|---|---|---|---|---|---|---|
| von | 5.02 s | 4.97 s | 5.28 s | 70.4 % | **2** | 0 |
| opendecider | 5.49 s | 5.47 s | 5.70 s | 85.2 % | 0 | 0 |
| laya | 5.83 s | 5.83 s | 6.04 s | **88.9 %** | 0 | 0 |
| kev-hosted | 15.86 s | 15.69 s | 18.60 s | 77.8 % | 0 | 0 |
| anarkali | — | — | — | — | — | superseded by the 31d3bfd fix — see below |

Findings:

- **anarkali: unblocked by `31d3bfd`** (every choice option now carries a
  description; noul questions keep absent — not empty — criteria). It accepts
  the full 15-question fan-out (200 in 1.1–3.8 s via the gate) and live turns
  complete (`jev 1130ms`), **but its confidences stay near-uniform (~0.2–0.26)
  with a strong timer bias** (routes "Tell me a joke" to target=timer), so
  turns clarify at gate 0.45. That is a model-quality problem — anarkali needs
  retraining on hey-jev-style questions, not a wire fix. (Original 422 finding:
  it rejected the fan-out because `app`'s `spotify` option had an empty
  description; the noul-criteria error only triggered hand-crafted payloads
  with explicit `{}`.)
- Decision latency scales ~linearly with question count (3-q probe 0.45–0.81 s
  → 15-q fan-out ~5–6 s): a real hey-jev turn pays this plus STT (~1.3 s) plus
  TTS. Even so the self-hosted candidates are **2.6–3.2× faster** than hosted
  KEV (15.9 s) and cost $0.
- **laya is the best self-hosted candidate so far** (88.9 % agreement, zero
  wrong-but-confident, 5.8 s) — matches its "conservative calibration"
  reputation; von agreed less (70.4 %) and produced 2 wrong answers at ≥ 0.9
  confidence.
- Hosted KEV itself wobbled on the timer phrase: `timer_action` confidence
  ~0.32 (set 0.49 vs none 0.32) — consistent with the live
  `timer_action 0.42–0.61` observations that motivated the timer_override.

## Deployment shape on the geekom

- Four decider units (`systemone-anarkali.service`, `systemone-von.service`,
  `systemone-opendecider.service`, `systemone-laya.service`) — **disabled at
  boot, owned by the gate** (see below). anarkali binds 0.0.0.0 (no host
  flag), the others 127.0.0.1 — the bearer key protects the exposed one.
- Per-candidate venvs and HF caches under `~/deciders/<name>/`
  (`von/hf`, `opendecider/hf`, `laya/hf`; anarkali downloads to its own
  cache dir).
- Shared bearer in `~/deciders/deciders.env` (mode 600, injected via
  `EnvironmentFile`) — regenerate by re-reading prod's `KEV_API_KEY`.
- Contract probe per server: a 3-question packed POST
  (`category`/`target`/`timer_action`, Bearer from `deciders.env`) to
  `http://127.0.0.1:890x/v1/systemone` — expect `answers` with
  `choice`/`confidence`.
- Manual override when wanted: `sudo systemctl start/stop systemone-<name>`
  (the gate tolerates external starts; its idle-stop will still clean up).

## Using it with hey-jev instances

- **Existing instances:** set `KEV_URL` (+ `JEV_GATE` if strict) in any
  instance `.env` — beta, prod, any combo dir — restart. The 6 combo
  instances make A/B trivial: point two at different candidates and compare
  live with the same spoken turns. URLs: `http://127.0.0.1:8901` (anarkali),
  `:8902` (von), `:8903` (opendecider), `:8904` (laya) — loopback beats the
  tunnel subdomains for on-box instances. Public names (any device or
  off-box use): `https://anarkali.nimes.in` etc., pending the CNAMEs below.
- **kev / liquid:** `https://kev.nimes.in` proxies the existing hosted KEV;
  for liquid set `KEV_URL=https://api.liquid.ai/decisions`,
  `KEV_MODEL=d1:free` **and** `KEV_API_KEY=<liquid_ key from
  console.liquid.ai>` (the shared decider key does not work there). Live
  config on the geekom: `~/combo/liquid-fish/.env` and `liquid-local/.env`.
- **New combo dirs (suggested, not created):** `kev-fish`/`kev-local` already
  prove the KEV plumbing; clone them as `anarkali-fish` etc. — one-line
  `.env` diff (`KEV_URL=http://127.0.0.1:8901`) + tunnel ingress entry.
- **Evaluation before promotion:** run a side-by-side window (hosted KEV and
  the candidate answering the same live turns — e.g. duplicate a combo
  instance with only `KEV_URL` changed), log `heard:` + answers from both
  journals, and require (a) parser parity, (b) agreement-rate on a labeled
  set, (c) no wrong-but-confident regressions at gate 0.45, before making a
  candidate the primary.
- **International caveat:** self-hosted candidates are English-only. International
  turns (prod `en,hr`) produce non-English decision text — keep hr instances on
  hosted backends until Laya's mmBERT router is validated on hr.

## Later code changes (explicitly NOT yet)

- Real multi-backend chain with per-candidate provenance labels
  (`backend: anarkali` instead of the cosmetic `kev`), per-backend timeouts
  (~5 s), and an escalation tier (local-first, unsure → hosted KEV/Jev).
- Version pinning + agreement-rate reporting for OpenDecider.
- Option-permutation stability test for Von.

Until then, the `.env`-only path above needs no code and is fully reversible.
