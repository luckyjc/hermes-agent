# tmux interactive handoff validation

Last validated: 2026-05-15 on host-native Hermes v0.12.0 with `hcc` launcher.

## Proven workflow

Use the helper script with an actual SESSION HANDOFF file:

```bash
python /home/lucky/docker/hermes/local-profiles/coding-cloud/skills/workflow/session-handoff/scripts/session_handoff_continue.py \
  /tmp/session-handoff-YYYYmmdd-HHMMSS.md \
  --launcher hcc \
  --tmux-interactive \
  --exit
```

The helper should:
1. Verify `TMUX` and current pane with `tmux display-message -p '#{pane_id}'`.
2. Start a new tmux split pane running plain interactive `hcc` by default. Use a new window only when explicitly requested with `--tmux-window`.
3. Wait for the interactive Hermes prompt before pasting. Do not rely on a fixed sleep alone.
4. Load the handoff file into a tmux buffer and paste it into the new pane with `paste-buffer -p -r`.
5. Send Enter to submit the prompt.
6. With `--exit`, send `/exit` to the old pane only after the new pane exists, prompt detection succeeded, and paste/submit succeeded. If any verification fails, leave the old pane open.

## Validation commands used

```bash
/home/lucky/.local/opt/hermes/.venv/bin/python3 -m py_compile \
  /home/lucky/docker/hermes/local-profiles/coding-cloud/skills/workflow/session-handoff/scripts/session_handoff_continue.py

python /home/lucky/docker/hermes/local-profiles/coding-cloud/skills/workflow/session-handoff/scripts/session_handoff_continue.py \
  /tmp/session-handoff-smoke.md \
  --launcher hcc \
  --tmux-interactive \
  --tmux-window-name handoff-smoke \
  --startup-wait 1 \
  --prompt-wait-timeout 20

tmux capture-pane -t handoff-smoke -p -S -120 > /tmp/handoff-smoke-capture.txt
grep -q 'SESSION HANDOFF' /tmp/handoff-smoke-capture.txt
```

Targeted Hermes skill-command tests:

```bash
cd /home/lucky/.local/opt/hermes
./scripts/run_tests.sh tests/agent/test_skill_commands.py -q
```

Expected result: `36 passed`.

## Long-term tracking

The durable copy of this skill now lives in the tracked Hermes runtime tree:

```text
/home/lucky/.local/opt/hermes/skills/workflow/session-handoff/SKILL.md
/home/lucky/.local/opt/hermes/skills/workflow/session-handoff/scripts/session_handoff_continue.py
```

The profile-local copy under `/home/lucky/docker/hermes/local-profiles/coding-cloud/skills/workflow/session-handoff/` remains useful for active `hcc` sessions, but local profile directories may be ignored by git. When changing this workflow, update or sync the tracked runtime copy before committing so the skill survives profile cleanup/rebuilds.

Related runtime commit: `477232773 fix: refresh skill slash command cache`, pushed to Azure `main` on 2026-05-15. That commit also added the tracked built-in skill files.

## Pitfalls

- `hermes skills list` may show a skill while a currently running interactive CLI still has a stale module-level `_skill_commands` cache. In Hermes v0.12.0, `/reload-skills` needed to refresh `cli.py`'s module-level `_skill_commands` from `get_skill_commands()` after `reload_skills()`.
- `agent.skill_commands.scan_skill_commands()` returns keys with a leading slash, e.g. `/session-handoff`; checks against `get_skill_commands()` may need the same shape.
- Do not test paste timing with a nonexistent handoff file; the helper correctly exits early before tmux behavior.
- Fixed startup sleeps are brittle. Prefer prompt detection via `tmux capture-pane` before paste, with a timeout that refuses to exit the old pane on failure.
- `tmux paste-buffer` replaces linefeeds with carriage returns by default. Use `-r` with `-p`; otherwise multiline handoffs can still submit one line at a time even though bracketed paste is enabled.
- Profile-local skills under `/home/lucky/docker/hermes/local-profiles/*` may be ignored by the repo `.gitignore`; verify persistence/commit strategy before assuming skill changes are tracked.
