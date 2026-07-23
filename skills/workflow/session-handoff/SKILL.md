---
name: session-handoff
description: "Continue current work in a fresh Hermes CLI session using compact repo-aware state and safe tmux automation."
version: 2.0.0
author: Athena
license: MIT
metadata:
  hermes:
    tags: [workflow, handoff, session, cli, hcc, continuity]
---

# Session Handoff

Use `/session-handoff` when the user wants to continue the current idea or workstream in a fresh Hermes CLI session. Do not use `/skill session-handoff`; `/skill` opens the skills hub.

The handoff file is the continuity artifact. The new session must read it and then verify live project/system state before acting.

## Defaults

- Write the canonical handoff to `/tmp/athena-session-handoffs/NEXT_SESSION.md`.
- Also create a persistent timestamped archive under `~/.local/state/hermes/session-handoffs/<profile>/`.
- In tmux, open a visible split pane anchored to the caller and keep the current pane open.
- Launch `hcc --yolo` by default.
- Send only a short instruction containing the handoff path; never paste the handoff body into the terminal.
- Use a new tmux window, background process, or old-pane exit only when explicitly requested.
- Use manual-file-only mode when requested or when tmux/launcher prerequisites are unavailable.

## Flags

- `--manual`: write/finalize the handoff and stop. This does not require tmux or `hcc`.
- `--no-yolo`: launch with normal approval behavior.
- `--yolo`: explicit restatement of the default, retained for compatibility.
- `--background`: start a one-shot continuation without an interactive pane.
- `--window`: open a tmux window instead of the default split.
- `--exit`, `--close`, or `--replace`: close the old pane only after the new interactive continuation is verified.
- Other safe launcher flags: pass with repeatable `--launcher-arg <arg>`.
- Other text: treat as the next-session focus, not a launcher argument.

## Project context first

For project-scaffolded repos, use repo-local artifacts instead of copying their contents into the handoff:

- `AGENTS.md`: stable project facts, contracts, commands, and constraints.
- `.hermes/bootstrap.md`: startup/read order.
- `docs/CURRENT_STATE.md`: mutable consolidated active state.
- `docs/TESTING.md`: validation commands.
- `CONTEXT.md` and `docs/adr/`: durable language and decisions.

Before finalizing, update `docs/CURRENT_STATE.md` when this session materially changed the active objective, blocker, proven state, validation plan, or next action. Consolidate and replace stale content; never treat it as an append-only session log. Do not touch it when no material project state changed.

The handoff should contain only the session delta and direct the next agent to authoritative artifacts. See `references/handoff-scenarios.md` for idea-development, AHO, interrupted-run, external-system, and sensitive-work variants.

## Handoff content

Target 400–800 words; hard maximum 1,200 words. Omit empty or irrelevant sections.

Required:

```text
SESSION HANDOFF

Goal:
- ...

Next-session objective:
- ...

Progress and decisions:
- ...

Authoritative artifacts:
- <absolute paths or URLs; reference, do not duplicate>

Validation and live state:
- ...

Open risks / unknowns:
- ...

Next steps:
1. ...
```

Add only when relevant:

- `Suggested skills`
- `Recommended AHO prompt shape`
- `External systems`
- `Communication preferences`

Include absolute repo path, branch, dirty/untracked state, validation results, and commit/push state for code work. Include verifiable handles for external changes. Never include secrets, credentials, payment data, raw restricted transcript content, or transcript dumps.

## Procedure

1. Parse flags and focus text.
2. Read the relevant project context files. Check live Git/system state cheaply when relevant.
3. Consolidate `docs/CURRENT_STATE.md` if project state materially changed.
4. Write the compact agent-authored body to a temporary draft file. It must begin with `SESSION HANDOFF`.
5. Finalize it deterministically; this discovers standard project context, records UTC time/profile/project root/Git branch/dirty path count, enforces the word budget, writes the canonical pointer, and creates the persistent archive:

```bash
python /home/lucky/docker/hermes/local-profiles/coding-cloud/skills/workflow/session-handoff/scripts/build_session_handoff.py \
  /tmp/session-handoff-draft.md \
  --project-root "$PWD"
```

6. If `--manual`, report the canonical and archive paths and stop.
7. Otherwise verify helper, launcher, and tmux target availability. In normal tmux use, launch the visible split:

```bash
python /home/lucky/docker/hermes/local-profiles/coding-cloud/skills/workflow/session-handoff/scripts/session_handoff_continue.py \
  /tmp/athena-session-handoffs/NEXT_SESSION.md \
  --launcher hcc \
  --tmux-interactive
```

The helper enables YOLO by default. Add `--no-yolo`, `--background`, `--tmux-window`, `--tmux-target <target>`, or `--exit` only when selected by the user-facing flags.

8. If prerequisites fail, preserve and report the canonical handoff path and the missing prerequisite. Do not claim a new session started and do not exit the current pane.

## Receiving a handoff

1. Read the handoff and its listed project context files first.
2. Treat handoff claims as a compact hypothesis. Re-check branch, status, diff, artifacts, tests, processes, and external state before acting.
3. Compare live state with the stated scope. Continue when they match; report drift rather than blessing stale claims.
4. Resume from `Next-session objective`, unless the live user message overrides it.

## Safety and validation

- Never stream or paste multiline handoff bodies with `send-keys`.
- The tmux helper waits for the prompt and bracket-pastes only the short file-path instruction.
- Exit the old pane only after the replacement pane, prompt, paste, and submit are verified.
- On paste cutoff, pane lock, or TUI injection failure, stop automation and fall back to the saved file path.
- Use `--dry-run` after helper changes, on a new host/profile, or when prerequisites are uncertain; skip it during ordinary handoffs.
- After changing this workflow, run Python compile checks, deterministic builder tests, dry runs for default/`--no-yolo`/`--manual`, and a synthetic interactive tmux smoke when safe. See `references/tmux-interactive-validation.md`.
