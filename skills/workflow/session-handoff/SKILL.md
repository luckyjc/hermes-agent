---
name: session-handoff
description: "End the current Hermes CLI session with a compact handoff summary for reopening in a fresh profile/session."
version: 1.0.0
author: Athena
license: MIT
metadata:
  hermes:
    tags: [workflow, handoff, session, cli, hcc, continuity]
---

# Session Handoff

Use this skill when the user wants to continue the current work in a fresh Hermes CLI session or another Hermes profile, while preserving enough context from the current conversation to keep going.

Support script: `scripts/session_handoff_continue.py` can launch a new continuation from the temp handoff file and, when explicitly requested and running under tmux, send `/exit` to the old pane. Validation notes and known pitfalls for the tmux flow are in `references/tmux-interactive-validation.md`.

The common local flow is to relaunch with `hcc`, but the handoff prompt should be profile-neutral unless the user names a target profile or command.

## Important limitation

A skill cannot safely type `/exit` into the current interactive CLI, relaunch the user's parent shell, and paste into the new prompt from inside the same agent turn. The current agent process does not control its own parent terminal input stream in a reliable, portable way.

So the default behavior is:
1. Produce a handoff prompt.
2. Write it to a temporary file, preferably under `/tmp`, and report the path.
3. If the user wants a manual transition, stop there; do not include `/exit` or launch commands unless asked.
4. If the user explicitly wants an automated transition, use the temp file as the single source of truth for the new-session prompt and launch the target Hermes CLI/profile with that prompt via its query flag when possible.
5. Do not pretend the current interactive session was terminated or replaced unless a tool-based automation path was explicitly executed and verified.

## Handoff procedure

When this skill is loaded or invoked:

1. Create a concise but complete handoff prompt titled `SESSION HANDOFF`.
2. Include only information needed to resume effectively:
   - User's goal and current intent.
   - What has already been done in this session.
   - Important decisions, assumptions, constraints, and preferences.
   - Relevant files, directories, repos, commands, services, tickets, URLs, job IDs, or process IDs.
   - Current state of any edits or running processes.
   - Validation already performed and results.
   - Known failures, risks, and open questions.
   - Exact next recommended steps.
3. If the task involved code or filesystem changes, include:
   - Absolute repo/path.
   - Branch and git status if available.
   - Tests/checks run and whether they passed.
   - Uncommitted files or commits made.
4. If the task involved external systems, include:
   - What was changed externally.
   - IDs/URLs/status codes or other verifiable handles.
   - Anything not yet verified.
5. Keep the handoff prompt compact enough to paste into a fresh session, but detailed enough for continuity. Prefer bullets over prose.
6. Write the handoff prompt to a temp file. Use a timestamped path such as `/tmp/session-handoff-YYYYmmdd-HHMMSS.md` unless the user specifies a path.
7. Do not include `/exit`, `hcc`, or other launch instructions in the handoff block itself. Keep transition mechanics separate from the saved context.
8. If the user asks for automated continuation, prefer an interactive tmux continuation when tmux is detected:

```bash
python /home/lucky/docker/hermes/local-profiles/coding-cloud/skills/workflow/session-handoff/scripts/session_handoff_continue.py /tmp/session-handoff-YYYYmmdd-HHMMSS.md --launcher hcc --tmux-interactive --tmux-exit-old
```

This opens a new tmux window running interactive `hcc`, pastes the handoff prompt from the temp file, submits it, and only then sends `/exit` to the old pane. If tmux is not detected, fall back to one-shot `hcc chat -q "$(cat file)"` or report the temp file path for manual use.

## Slash-command invocation

Use the skill slash command directly:

```text
/session-handoff
```

Do not use `/skill session-handoff` in this Hermes version. `/skill` is routed to the interactive skills hub, where the first argument is treated as a hub action, so it fails with `Unknown action: session-handoff`.

Hermes builds bare slash commands for installed skills by scanning skill names, so this skill's command is `/session-handoff`. In Hermes v0.12.0 there was a stale CLI cache bug where `/reload-skills` updated `agent.skill_commands` but not `cli.py`'s module-level `_skill_commands`; if `/session-handoff` still says `Unknown command`, restart the CLI or use the patched runtime where `_reload_skills()` refreshes the CLI cache too.

## Optional automated continuation path

If the user explicitly asks to automate the terminal handoff:

1. Save the handoff prompt to a temporary file under `/tmp` or the user's workspace.
2. Verify the target launcher exists, for example `command -v hcc`.
3. Use the bundled helper script when available. Always dry-run first:

```bash
python /home/lucky/docker/hermes/local-profiles/coding-cloud/skills/workflow/session-handoff/scripts/session_handoff_continue.py /tmp/session-handoff-YYYYmmdd-HHMMSS.md --launcher hcc --tmux-interactive --tmux-exit-old --dry-run
```

4. If the dry run detects `tmux_current_pane`, run the interactive handoff:

```bash
python /home/lucky/docker/hermes/local-profiles/coding-cloud/skills/workflow/session-handoff/scripts/session_handoff_continue.py /tmp/session-handoff-YYYYmmdd-HHMMSS.md --launcher hcc --tmux-interactive --tmux-exit-old
```

This starts plain interactive `hcc` in a new tmux window, waits for the interactive prompt, loads the handoff file into a tmux buffer, pastes it into the new pane, submits it, and only then sends `/exit` to the old pane.

5. Only send `/exit` to the old pane when:
   - the user explicitly requested automated handoff,
   - `TMUX` is set and `tmux display-message -p '#{pane_id}'` returns a pane id,
   - the new interactive tmux pane is verified,
   - the handoff prompt was pasted and submitted successfully.
6. If tmux is not detected, do not try to exit the old session. Start a one-shot continuation with `hcc chat -q "$(cat file)"` or report the temp file path for manual use.

This approach creates the new continuation context programmatically without needing clipboard paste. The tmux path preserves an interactive session for continued work.

## Handoff prompt template

```text
SESSION HANDOFF

Goal:
- ...

Current state:
- ...

Completed this session:
- ...

Important context and constraints:
- ...

Files/repos/services involved:
- ...

Validation performed:
- ...

Open risks / unknowns:
- ...

Next steps:
1. ...
2. ...
3. ...

Communication preferences:
- Keep responses direct and operational.
- Use tools to verify current system/file/git state before making factual claims.
```

## Quality bar

- Do not dump raw transcript text unless the user asks for it.
- Do not include secrets, tokens, passwords, private keys, or payment details.
- If something is uncertain, label it as uncertain.
- If relevant state can be checked cheaply with tools before handoff, check it.
- End with a clear instruction for the user to exit and relaunch the target Hermes CLI/profile.
