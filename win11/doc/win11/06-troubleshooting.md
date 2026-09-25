# Troubleshooting (Windows 11 / web remote)

## `python` opens the Microsoft Store

Store execution-alias stub: **Settings > Apps > Advanced app settings > App
execution aliases** → disable `python.exe`/`python3.exe`. Or use `py -3`.

## `pip install -r requirements.txt` fails on pyobjc (repo root)

That's the **original repo** — use the port (`cd win11`, clean
requirements.txt) or install root deps minus pyobjc
([02-install.md](02-install.md) path B).

## Missing keys at startup

Exact messages tell you what's absent:

- `need FISH_AUDIO_API_KEY in Credential Manager or .env` — always required
- `need a decision backend ...` — set one of: `TYPESAFE_API_KEY`, or
  `KEV_URL` + `KEV_API_KEY` (both), or `OPENROUTER_API_KEY`

Check: `.env` in `win11/`, no quotes, no trailing spaces. With KEV, **both**
`KEV_URL` and `KEV_API_KEY` must be non-empty or the app silently stays on
Typesafe (and 401s there with a KEV key).

## 401 / wrong backend

- Typesafe key wrong/expired → re-paste via Keys… or `.env`.
- KEV: the key must be the KEV deployment's key, not a Typesafe one.
- OpenRouter decisions fallback: any valid OpenRouter key works; the model
  resolves to `typesafe/jev-1.13-YYYYMMDD`.

## She keeps saying "sorry, say that again"

Below the gate she re-asks (twice, then gives up). Read the trace:

- `> heard:` garbled → mic/STT (`--list-devices`, `--device`).
- Transcript fine, confidences low → KEV's small model runs hot; correct
  answers regularly land 0.3–0.6. The gate auto-drops to 0.45 with KEV
  (`JEV_GATE` to override). See [../jev-compatible.md](../jev-compatible.md) §2.

## Mic: silent, or "Error querying device -1"

- **Settings > Privacy & Security > Microphone > desktop apps** on.
- If Windows has **no default input**, the port auto-picks the first mic and
  logs it (`[mic] no default input device...`). If no mic endpoint exists at
  all (`query_devices` shows only outputs — this PC's case), desktop
  `--wake`/PTT cannot work: use the web remote from a phone.
- Enumerate: `--list-devices`; pick: `--device <name-or-index>`.

## Web remote: page shows "Disconnected — retrying…"

- Backoff caps at 8s; pressing HOLD TO TALK while disconnected triggers an
  instant reconnect.
- If it never connects: restart the server (`restart-remote.ps1`) and check
  the NPM proxy host has **Websockets Support** enabled and the cert valid.

## Web remote: tiles/history/presses do nothing after a code change

Web files are served from disk per request (reload the page), but **Python
changes need a restart** — `powershell -File restart-remote.ps1`.

## Web remote: "Access token required" prompt

`REMOTE_TOKEN` is set and the device hasn't stored it. Paste the token once
(overlay, Enter or Save & connect) — it persists in that browser's
localStorage. Clients with their own Fish key in Settings bypass the token.

## Turn costs / cost badge missing

The badge appears after a completed turn (Jev + LLM costs; TTS free-tier = 0;
replay turns show none). If missing entirely, the server predates the cost
feature → restart.

## Cancel does nothing

The ✕ stops the turn at its **next checkpoint** (post-Jev, pre-LLM,
pre-speech). A turn already inside the LLM/TTS request finishes that stage
first — the button still shows until the server answers Ready.

## Volume commands fail with a PowerShell/Add-Type error

The WASAPI helper compiles inline C# on first use; some antivirus policies
block `Add-Type`. Allow the PowerShell child process, or pre-warm once:
`python -c "import siri; siri.volume()"`.

## Dark mode toggles but doesn't apply until Explorer restarts

The `WM_SETTINGCHANGE` broadcast needs a non-elevated sender — if the app
runs as Administrator the broadcast can be dropped. Restart non-elevated.

## Sleep hibernates instead of sleeping

`SetSuspendState` hibernates when hibernation is enabled:
`powercfg /hibernate off` (admin) if you want real sleep.

## Spotify play/pause does nothing

Media keys go to the active global media session — another app (YouTube tab)
may own it. Also use the desktop Spotify app, not the web player.

## GLM answers sometimes empty

Reasoning models can return `content: null` when the token budget is too
small — `LLM_MAX_TOKENS` defaults to 300. Reasoning itself cannot be
disabled on this endpoint (400 "mandatory"); the app sends `effort: low`.

## Weather/skills fail with non-JSON or timeouts

All free APIs (wttr.in, frankfurter, Wikipedia, icanhazdadjoke, BBC RSS) are
rate-limited occasionally; skills degrade to the `skill_fail` line (and
Wikipedia to the LLM). Retry or wait a minute.

## Bulk import recognized fewer lines than pasted

The parser tolerates smart quotes, zero-width chars, NBSP, `export`
prefixes, CRLF, quoted values — and auto-falls back to a token parser when
ntfy/mobile copies collapse newlines into spaces. The status message lists
exactly what was recognized and what was ignored; if lines are missing, the
**paste itself was truncated** (notification-tray copies do that) — open the
message in the ntfy app and copy the full body.

## Alarms/timers vanish after restart

They shouldn't — `timers.json` saves every mutation and reloads at startup.
If the file is empty after a restart, check the server stopped cleanly and
that `win11/timers.json` exists.

## Console mojibake / `UnicodeEncodeError`

Use Windows Terminal (UTF-8) or `$env:PYTHONUTF8="1"`.
