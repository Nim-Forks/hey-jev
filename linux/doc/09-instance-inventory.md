# hey-jev fleet — instance inventory (meeting summary)

2026-10-06 · 21 running instances on 2 machines · all speaking the same
voice assistant stack (Whisper STT → System One decisions → LLM answers →
Fish/Chatterbox TTS) · public token: `deva`.

## Instances

| Instance | URL | Release | Decision | Voice | Personas | Speed (warm turn) | Cost/decision | Notes |
|---|---|---|---|---|---|---|---|---|
| **alpha** (win11 K12) | https://hey-jev.overgate.online | `900e206` | hosted KEV (12–15 s) | Chatterbox | ✓ | ~15–25 s | $0.000037 | personal daily driver, NPM front |
| **beta** (geekom) | https://hey-jev.overgate.site | `f8da21e` | hosted KEV (12–15 s) | Chatterbox | ✓ | ~15–25 s | $0.000037 | test box |
| **prod** (geekom) | https://hey-jev.nimes.in | `f8da21e` | hosted KEV (12–15 s) | Fish | ✗ | ~17–19 s | $0.000037 | family/stable, tunnel front |
| kev-fish | https://kev-fish.nimes.in | `f8da21e` | hosted KEV (15.9 s) | Fish | ✗ | ~17 s | $0.000037 | benchmark baseline |
| kev-local | https://kev-local.nimes.in | `f8da21e` | hosted KEV (15.9 s) | Chatterbox | ✓ | ~15–20 s | $0.000037 | legacy comparison |
| jev-fish | https://jev-fish.nimes.in | `f8da21e` | OpenRouter* (0.3–0.9 s) | Fish | ✗ | ~2–5 s | $0.000072 | Typesafe slot (key pending) |
| jev-local | https://jev-local.nimes.in | `f8da21e` | OpenRouter* | Chatterbox | ✓ | ~2–3 s cached / +5–20 s fresh | $0.000072 | Typesafe slot |
| or-fish | https://or-fish.nimes.in | `f8da21e` | OpenRouter (0.3–0.9 s) | Fish | ✗ | ~2–5 s | $0.000072 | snappiest hosted turns |
| or-local | https://or-local.nimes.in | `f8da21e` | OpenRouter | Chatterbox | ✓ | ~2–3 s cached / +5–20 s fresh | $0.000072 | personas + speed |
| anarkali-fish | https://anarkali-fish.nimes.in | `f8da21e` | anarkali self-hosted | Fish | ✗ | n/a — give_up | $0 | ❌ 422 on real fan-out — needs brain.py question-set fix |
| anarkali-local | https://anarkali-local.nimes.in | `f8da21e` | anarkali self-hosted | Chatterbox | ✓ | n/a — give_up | $0 | same |
| von-fish | https://von-fish.nimes.in | `f8da21e` | von self-hosted (5.0 s, 70.4 % agreement) | Fish | ✗ | ~8 s | $0 | ⚠ 2 wrong answers at ≥0.9 conf |
| von-local | https://von-local.nimes.in | `f8da21e` | von self-hosted | Chatterbox | ✓ | ~8–12 s | $0 | same |
| opendecider-fish | https://opendecider-fish.nimes.in | `f8da21e` | opendecider self-hosted (5.5 s, 85.2 %) | Fish | ✗ | ~7–8 s | $0 | fastest $0 decider |
| opendecider-local | https://opendecider-local.nimes.in | `f8da21e` | opendecider self-hosted | Chatterbox | ✓ | ~8–13 s | $0 | |
| laya-fish | https://laya-fish.nimes.in | `f8da21e` | **laya self-hosted (5.8 s, 88.9 %)** | Fish | ✗ | ~8 s | $0 | best self-hosted decider |
| laya-local | https://laya-local.nimes.in | `f8da21e` | laya self-hosted | Chatterbox | ✓ | ~8–13 s | $0 | |
| liquid-fish | https://liquid-fish.nimes.in | `f8da21e` | **Liquid d1:free (0.9 s, conf 0.995)** | Fish | ✗ | **~4 s (measured)** | **$0** (free tier) | **recommended daily driver** |
| liquid-local | https://liquid-local.nimes.in | `f8da21e` | Liquid d1:free | Chatterbox | ✓ | ~4–6 s cached / +5–7 s fresh | $0 | recommended for personas |
| clef-fish | https://clef-fish.nimes.in | `666770f` | Clef 27B via gate (0.6 s, conf 0.95/0.99) | Fish | ✗ | ~3.8–6.1 s (measured) | $~0.00006 | deterministic, image input; 2026-10-06 |
| clef-local | https://clef-local.nimes.in | `666770f` | Clef via gate | Chatterbox | ✓ | ~4–6 s cached / +5–7 s fresh | $~0.00006 | personas on Clef |

\* `jev-*` decisions currently served by OpenRouter until a `TYPESAFE_API_KEY`
is pasted into their `.env`. Speed = full turn (STT + decision + TTS reply),
warm; chatterbox instances add 5–7 s per fresh reply line, 0 s cached. Decider
latencies are from the 15-question fan-out stress.

## Cost model

| item | cost |
|---|---|
| Fish Audio TTS | $0 (`s2.1-pro-free`, free until end of Nov 2026) |
| Chatterbox TTS | $0 (local CPU on alpha/beta/geekom) |
| Liquid d1:free decisions | $0 (free tier) |
| Clef decisions (Workers AI, via gate) | $~0.00006 → $0.06 / 1000 turns (Clef-flash variant: ~$0.02) |
| self-hosted deciders (laya/von/opendecider/anarkali) | $0 (geekom CPU, on-demand gate ≈ 54 MB idle) |
| hosted KEV decisions | $0.000037 → $0.04 / 1000 turns |
| OpenRouter decisions | $0.000072 → $0.07 / 1000 turns |
| LLM answers (glm-5.3-flash) | same for every instance, question turns only |

Fleet cost is effectively **$0–$0.07 per 1,000 turns** — the real constraint
is the geekom's 11 GiB RAM, managed by the on-demand decider gate.

## Recommended order

Use in this order; fall down the list only when the previous one is unavailable:

| # | instance | URL | why this position |
|---|---|---|---|
| 1 | liquid-fish | https://liquid-fish.nimes.in | free + fastest-calibrated (0.9 s decisions, ~4 s turns) — default |
| 2 | clef-fish | https://clef-fish.nimes.in | faster still (0.6 s decision) + deterministic + images; costs $0.06/1k turns; validate `confidence` semantics first |
| 3 | laya-fish | https://laya-fish.nimes.in | best self-hosted fallback (88.9 % agreement) if both hosted paths fail |
| 4 | opendecider-fish | https://opendecider-fish.nimes.in | second $0 fallback (85.2 %, fastest self-hosted probe) |
| 5 | or-fish | https://or-fish.nimes.in | hosted fallback — snappy, costs $0.07/1k turns |
| 6 | liquid-local | https://liquid-local.nimes.in | personas, same #1 decisions |
| 7 | clef-local | https://clef-local.nimes.in | personas on Clef |
| 8 | laya-local | https://laya-local.nimes.in | personas, self-hosted decisions |
| 9 | von-fish | https://von-fish.nimes.in | only if 1–8 are down — watch the 2 wrong-but-confident answers |
| 10 | kev-fish | https://kev-fish.nimes.in | legacy — 15 s decisions, keep as a benchmark, not a daily |

Skip: `anarkali-*` (broken until brain.py fix), `jev-*` (duplicate of or-\*
until a TypeSafe key lands), `kev-local` / `or-local` (personalas are covered
by liquid-local / laya-local at better speed/cost).

For automation, the same order is what a decision escalation chain should
implement: liquid → laya → opendecider → or → von → kev.

## Verdict

- **Recommended**: `liquid-fish` / `liquid-local` — fastest (0.9 s decisions,
  ~4 s full turns), best calibrated, $0.
- **Best self-hosted** (no vendor): `laya-*` — 88.9 % routing agreement.
- **Pending**: anarkali needs a small `brain.py` fix; jev-\* needs a TypeSafe
  key; alpha is one release behind (`900e206` → pull + restart to reach
  `f8da21e`).

Details: `linux/doc/07-combo-instances.md` (combos), `08-systemone-backends.md`
(deciders, gate, memory), stress tables in both.
