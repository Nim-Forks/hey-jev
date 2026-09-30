# /spec-init — command documentation

> Canonical copy: `.agents/command/spec-init.md` (Kilo loads commands from `.kilo/command/`, which currently rejects command frontmatter — see the note at the bottom). This file documents the command for the tts-alternatives feature and is the copy used to drive its specs.

---
description: Initialize the spec workflow for a feature
---
# Spec Init

Initialize the spec workflow for: **$ARGUMENTS**

## Steps

1. **Resolve the feature name.** Convert the arguments to a kebab-case `feature-name`. If the argument is empty, ask for the feature name. Do NOT create anything until the name is known.
2. **Pick the entry point** (record in `.config.kiro`):
   - `requirements-first` (default) — business needs clear, technical approach uncertain.
   - `design-first` — technical vision clear, requirements derived from it.
   Ask the user only if the arguments do not state it.
3. **Check for prior discovery.** If a `research.md` already exists for the feature (e.g. `alternatives/doc/research.md`), link it from the requirements stub and prefer `design-first` — do not redo discovery.
4. **Choose the spec home**, then scaffold it with exactly three files:
   - Default home: `.agents/specs/<feature-name>/` (kiro tooling convention).
   - Feature-local home: if the feature owns a top-level folder (e.g. `alternatives/`), scaffold in its existing docs folder so discovery and spec ship together — for this feature that is `alternatives/doc/` (research.md, spec-init.md, .config.kiro, init.json, requirements.md, later design.md + tasks.md). Keep exactly one home — move, never duplicate.
   - `.config.kiro` — one line JSON: `{"specId": "<feature-name>", "workflowType": "<entry-point>", "specType": "feature"}`
   - `init.json` — copy of `.agents/settings/templates/specs/init.json` with every `{{PLACEHOLDER}}` filled:
     - `ticket_id` / `feature_name`: the feature name
     - `branch`: the current git branch (never invent one)
     - `created_at` / `updated_at`: current ISO-8601 UTC timestamp
     - `language`: `"en"` unless the user says otherwise
     - `phase`: `"initialized"`
     - `summary`: one sentence from the user's description
     - `approvals` all `false`, `ready_for_implementation`: `false`
   - `requirements.md` — from `.agents/settings/templates/specs/requirements-init.md`, with `{{PROJECT_DESCRIPTION}}` replaced by the user's description (plus a link to any prior research doc). Leave the `## Requirements` section untouched for the requirements phase.
5. **Never fabricate content.** Do not generate requirements, design or tasks in this command — that belongs to the `/spec-requirements`, `/spec-design`, `/spec-tasks` phases.
6. **Report** the created paths, the chosen entry point and the next command to run.

## Rules (from .agents/steerings/spec_workflow.md)

- One active spec workflow at a time; refuse politely if another spec is mid-flight.
- Phases gate on user approval recorded in `init.json`; nothing advances silently.
- No parallel spec creation; queue instead.

---

## Note on Kilo command loading

Kilo reads project commands from `.kilo/command/*.md`. In this environment every frontmatter variant — including the documented minimal example and no frontmatter at all — fails the CLI validator with `Failed to parse frontmatter: No context found for instance`. The command therefore lives in `.agents/command/` and is applied manually (or via this doc) until the validator accepts command files.
