# Handoff scenarios

Use these only when the scenario applies. The main handoff should remain compact and reference durable project artifacts instead of repeating them.

## Project-scaffolded repositories

Treat repo-local files as the continuity source of truth:

- `AGENTS.md`: stable operating context, architecture constraints, commands, and sources of truth.
- `.hermes/bootstrap.md`: short startup/read order.
- `docs/CURRENT_STATE.md`: consolidated active objective, blockers, scope, validation, and next-session notes.
- `docs/TESTING.md`: copy-pasteable validation commands.
- `CONTEXT.md`: durable domain vocabulary.
- `docs/adr/`: durable decisions.

Before handoff, update `docs/CURRENT_STATE.md` when the active objective, blocker, proven state, or next action changed materially. It is a mutable snapshot, not an append-only log. Replace stale sections and consolidate old notes rather than adding another dated narrative. Do not rewrite it when the current session made no material project-state change.

The handoff should then carry only the session delta: what changed since those files were last accurate, current validation/dirty state, unresolved risks, and the exact next-session objective.

## Idea development

Capture:

- The idea being developed and the decision now under consideration.
- Decisions made, options rejected, and why.
- The strongest unresolved question.
- The next concrete artifact or experiment.

Prefer `Progress and decisions` over a chronological completed-task list. Put `Next-session objective` immediately after `Goal`.

## AHO or autonomous continuation

Add a compact `Recommended AHO prompt shape` containing:

- Absolute repo path and approved milestone.
- Hard no-go boundaries.
- Validation gates and expected artifacts.
- Commit/push policy.
- Explicit Athena supervision: inspect diffs, verify claims, run gates, then commit/push.

Use a broad safe milestone, not a tiny edit. For sensitive docs/governance work, default to docs/audit/no-runtime-authority unless runtime behavior was explicitly approved.

## Interrupted provider or agent run

Recover state before writing the handoff:

1. Inspect session history when available.
2. Check Git branch, status, recent commits, diff stat/name-status, and untracked files.
3. Run only cheap targeted checks needed to classify the batch.
4. Label the batch `complete`, `in progress`, or `unproven`.

Never bless or commit a broad dirty batch solely because a narrow test passed.

## External systems

Include only verified handles and state:

- What changed externally.
- Relevant IDs, URLs, status codes, or timestamps.
- What remains unverified.
- Any action that must not be repeated.

Never include credentials, payment details, private keys, tokens, or restricted transcript content.

## Sensitive work

Keep the handoff metadata-safe. Reference governed artifacts by path or ID. Do not paste raw sensitive content, source URIs, transcript excerpts, secrets, or private identifiers into the handoff or terminal.

## Compaction or stale handoff recovery

A handoff is a starting hypothesis, not current proof. The new session must re-read project context and verify live repo/system state. Live user instructions override handoff text and compaction summaries.
