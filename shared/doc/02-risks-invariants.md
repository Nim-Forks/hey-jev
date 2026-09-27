# Risks, invariants, and rollback

## Hard invariants (the rules the refactor must not break)

1. **Global-patch contract.** `remote_server` customises turns by patching
   module attributes (`say`, `MEMORY_SINK`, `MEMORY_CURRENT`,
   `TURN_CANCEL["flag"]`, keys on `config`). Every read site in `brain`
   must therefore be `config.X` / `brain.X` — **never** a local variable,
   default argument, or `from … import name` binding (from-imports freeze
   the value and the patch stops working). The two past bugs of exactly
   this shape: the `say` patch applied to the wrong module, and a stale
   `memory=MEMORY_CURRENT` copy.
2. **RLock on timers.** `TIMERS_LOCK` must stay an `RLock` — `save_timers()`
   is called from inside the lock.
3. **`TURN_CANCEL` reset.** Set `False` at every turn start and in the
   finally block — cancel is cooperative, checkpoints only.
4. **Per-connection state shape.** `sessions[conn] = {"keys": {…},
   "memory": […], "uses": int, "ntfy": str}` — `begin_turn` reads
   `["keys"]`, memory sink reads the whole session. Do not flatten.
5. **Quota counts only server-Fish turns.** `using_server_keys` is decided
   by the *absence of the client's FISH key* — not by the decision backend.
6. **Cost never spoken.** `LAST_TURN_COST` → data messages/headers only.
7. **Secrets never in git.** `.env`, `timers.json`, `~/.cloudflared` stay
   out of the tree; hooks and placeholders only.
8. **STT spec is platform-read, shared-resolved.** `WHISPER_LANGUAGES` comes
   from each platform's `.env`; `shared/stt.whisper_spec()` decides the
   model/language (multilingual `small` when cached + non-en configured).
   Both platforms gain/lose languages by editing one variable — no
   platform-specific STT code.

## Risks

| Risk | Likelihood | Mitigation |
| --- | --- | --- |
| A `from config import X` sneaks in → patch silently ignored | medium | grep gate: `grep -nE "^from shared|^import shared|^ +[A-Z_]+ =" brain.py` in review; keep reads as `config.X`/`brain.X` |
| Platform hook unset when a turn runs (import-order mistake) | low | `config.py` asserts both hooks are set in `handle()` start; loud error, no silent misroute |
| Two platform folders drift after refactor (someone edits brain in win11) | medium | after migration the platform files contain **no** brain symbols — grep for `def decide|QUESTIONS|fetch_tts` in `win11/`+`linux/` should be empty |
| Whisper model reload loops on spec change | low | `_Whisper.get` already keys on model name; spec is boot-stable |
| Linux-box live regression after linux port | medium | deploy sequence reuses the working `install.sh`/service; git rollback = `git checkout 72e05d7 -- linux` and redeploy |
| Web pages drift | eliminated | single `shared/web` source; platform folders hold no copies |

## Rollback

The refactor is a pure move on `feature-shared`:

- `git switch release` → both platforms keep running from the pre-refactor
  commits (`72e05d7`)
- Linux-box rollback: redeploy from the release tree and restart the\n  service (`sudo systemctl restart hey-jev`)
- Windows rollback: same shape — no data migration exists to undo
  (`timers.json` format unchanged)

## Verification gates (before any merge to release)

- `python -c "import siri, remote"` per platform
- `--text` turn + one timer set/fire per platform
- web remote: one voice turn + one typed turn, cancel mid-Thinking, quota
  message after `SERVER_KEY_LIMIT` (set limit 0 temporarily), token-gate
  prompt, memory save/recall, one skill per category (weather, rain,
  sunrise, currency, wiki, joke, news)
- grep gate: no brain symbols left in platform folders; no `from … import`
  of mutable config names in shared modules
- Linux box: `systemctl status hey-jev` + one remote turn via
  `https://hey-…/health` page
- win11 multilingual gate: a Fish-synthesized phrase in a configured
  non-English language through a web turn → correct transcript + reply in
  that language (only when `WHISPER_LANGUAGES` is set and the multilingual
  model is cached; en-only fallback otherwise)
