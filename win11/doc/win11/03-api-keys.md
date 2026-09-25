# API keys & configuration on Windows 11

Everything lives in `.env` (in `win11/`, git-ignored, wins over Credential
Manager) or Credential Manager via the window's **Keys…** panel (`keyring`,
service `com.heyjev.win`). Template: `Copy-Item .env.example .env`.

## Decision backend — priority: KEV > Typesafe > OpenRouter

| Key | Priority | Notes |
| --- | --- | --- |
| `KEV_URL` + `KEV_API_KEY` | 1 (if both set) | your KEV deployment, `/v1/systemone`, model `jev-latest` (aliased) |
| `TYPESAFE_API_KEY` | 2 | Typesafe cloud Jev |
| `OPENROUTER_API_KEY` | 3 | OpenRouter's decisions API (`https://openrouter.ai/api/alpha/decisions`, model `typesafe/jev-1.13`) — also required for LLM answers in any mode |

`JEV_MODEL` overrides the OpenRouter decisions model string.

## LLM answers

| Key | Default | Notes |
| --- | --- | --- |
| `LLM_MODEL` | `anthropic/claude-haiku-4.5` | any OpenRouter chat model; reasoning models get `reasoning: {effort: "low"}` automatically (GLM's reasoning cannot be disabled) |
| `LLM_MAX_TOKENS` | `300` | headroom for reasoning models; answers are one short sentence |

The LLM gets context only when Jev's fan-out says it's needed (`needs_time`,
`needs_machine` noul questions) plus the client's memory facts.

## Voice

| Key | Notes |
| --- | --- |
| `FISH_AUDIO_API_KEY` | **always required** — https://fish.audio; `s2.1-pro-free` free on the API until end of November 2026 |

## Remote web server

| Key | Default | Notes |
| --- | --- | --- |
| `REMOTE_FRONT` | `none` | `none \| npm \| coolify \| tunnel` — pure proxies; the server always binds plain HTTP |
| `REMOTE_PORT` | `8765` | local bind port (NPM forwards to it; enable **Websockets Support** + DNS-01 cert in NPM) |
| `REMOTE_HOST` | `0.0.0.0` | bind address (`127.0.0.1` = PC-only, behind NPM/tunnel) |
| `REMOTE_TOKEN` | empty | shared secret; if set, web clients need it (Settings page) or their own keys |
| `SERVER_KEY_LIMIT` | `10` | free turns when the client uses the server's Fish key (counted client-side in localStorage; turns with the client's own key don't count) |

Per-user keys + memory + ntfy topic live in each browser's localStorage
(Settings page: paste-only fields, bulk `.env` import/export — `NTFY_URL`
and `ALERT_MESSAGE` included — server-side "Test keys"). The server never
persists them.

## Push + misc

| Key | Notes |
| --- | --- |
| `NTFY_URL` | optional server-owner push channel; timer/reminder alerts + missed-offline reminders |
| `ALERT_MESSAGE` | optional default spoken/pushed alert for timers set without a label (per-device override in Settings; labeled reminders always say their label) |
| `JEV_GATE` | confidence gate override; default 0.45 with KEV, 0.65 with Typesafe/OpenRouter |

## Startup gate

`FISH_AUDIO_API_KEY` + one decision backend. Missing everything produces:
`need a decision backend in Credential Manager or .env: ...`

The trace prints `backend: <name> (<model>)` per decision; every turn also
reports its cost (Jev + LLM) in the trace, the web page badge and the
`X-Cost` HTTP header — never spoken.

## Keep it secret

`.env` holds live credentials; Credential Manager entries are per-user,
DPAPI-protected — the safer default. Rotate at the provider if anything
leaks.
