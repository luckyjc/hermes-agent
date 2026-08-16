# tmux interactive handoff validation

The helper must send only a short instruction containing the canonical handoff path. It must never paste the handoff body into a terminal.

## Deterministic checks

```bash
python -m py_compile \
  scripts/build_session_handoff.py \
  scripts/session_handoff_continue.py

python scripts/session_handoff_continue.py \
  /tmp/athena-session-handoffs/NEXT_SESSION.md \
  --launcher hcc \
  --tmux-interactive \
  --dry-run

python scripts/session_handoff_continue.py \
  /tmp/athena-session-handoffs/NEXT_SESSION.md \
  --launcher hcc \
  --no-yolo \
  --tmux-interactive \
  --dry-run
```

Expected default dry-run launcher arguments include `--yolo`; the opt-out run must not include it. `--manual` must work even when the requested launcher does not exist.

## Interactive smoke

Use a synthetic handoff whose next-session objective asks the receiver to reply with exactly:

```text
HANDOFF TEST RECEIVED AS ONE PROMPT
```

Launch it in a split without `--exit`. Capture the new pane and confirm:

1. One receiving prompt contains the complete canonical file path instruction.
2. The receiver read the file and emitted the fixed phrase.
3. No handoff-body text was pasted into the input pane.
4. No repeated submission or interrupt loop occurred.

Clean up the test pane with `/exit` after verification.

## Safety gates

- Resolve and anchor to the caller pane or an explicit `--tmux-target`.
- Wait for the interactive prompt; do not rely only on fixed sleep.
- Use a named tmux buffer and `paste-buffer -p -r` for the short path instruction.
- Verify replacement pane, prompt, paste, and submit before honoring `--exit`.
- If tmux is unavailable, preserve the handoff file and use manual fallback.
- On cutoff, pane lock, or TUI input regression, stop retrying automation. Never fall back to line-by-line `send-keys`.

## Persistence

The active profile copy is under:

```text
/home/lucky/docker/hermes/local-profiles/coding-cloud/skills/workflow/session-handoff/
```

The tracked runtime copy is under:

```text
/home/lucky/.local/opt/hermes/skills/workflow/session-handoff/
```

After a reviewed change, sync both copies and run validation from the tracked runtime repository before committing.
