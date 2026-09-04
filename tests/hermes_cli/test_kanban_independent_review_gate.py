"""Structural independent-review policy and lifecycle regressions."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from hermes_cli import kanban_db as kb
from hermes_cli import kanban_db_connect as kbc
from hermes_cli import kanban_decompose as decomp
from hermes_cli import kanban as kanban_cli


MISSING_REVIEWER = (
    "review required: name an eligible reviewer profile different from the implementer "
    "with reviewer=<profile> (CLI: --reviewer <profile>)"
)
SELF_REVIEW = (
    "independent review required: reviewer profile 'builder' matches implementer profile "
    "'builder'; choose a different eligible reviewer with reviewer=<profile> "
    "(CLI: --reviewer <profile>)"
)
MISSING_VERDICT = (
    "review required: task cannot complete without review_verdict='approve' from reviewer "
    "'code-reviewer'; claim the review as that profile and call "
    "kanban_complete(..., review_verdict='approve')"
)


@pytest.fixture
def board(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    home = tmp_path / ".hermes"
    home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    for name in ("builder", "code-reviewer", "security-reviewer", "architecture-reviewer", "reviewer"):
        (home / "profiles" / name).mkdir(parents=True, exist_ok=True)
    path = home / "kanban.db"
    kb._INITIALIZED_PATHS.discard(str(path.resolve()))
    with kbc.connect_closing(path) as conn:
        yield conn


def _required_task(conn, *, reviewer: str | None = "code-reviewer") -> str:
    return kb.create_task(
        conn,
        title="Implement material backend change",
        assignee="builder",
        task_type="implementation",
        risk_level="material",
        review_policy="required",
        reviewer_profile=reviewer,
    )


def _request_and_claim_review(conn, task_id: str):
    implementation = kb.claim_task(conn, task_id, claimer="builder:implementation")
    assert implementation is not None
    assert kb.request_review(
        conn,
        task_id,
        summary="Implementation and focused tests are ready.",
        expected_run_id=implementation.current_run_id,
    )
    review = kb.claim_review_task(conn, task_id, claimer="reviewer:independent")
    assert review is not None
    return implementation, review


def _review_mutation_snapshot(conn, task_id: str) -> tuple:
    """Persisted task, run, and event state used by fail-closed regressions."""
    task = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    runs = conn.execute(
        "SELECT * FROM task_runs WHERE task_id = ? ORDER BY id", (task_id,),
    ).fetchall()
    events = conn.execute(
        "SELECT * FROM task_events WHERE task_id = ? ORDER BY id", (task_id,),
    ).fetchall()
    return tuple(task), tuple(map(tuple, runs)), tuple(map(tuple, events))


def test_legacy_task_migration_defaults_to_no_review_and_still_completes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home = tmp_path / ".hermes"
    home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    path = home / "legacy-kanban.db"
    raw = sqlite3.connect(path)
    raw.executescript(
        """
        CREATE TABLE tasks (
            id TEXT PRIMARY KEY, title TEXT NOT NULL, body TEXT, assignee TEXT,
            status TEXT NOT NULL, priority INTEGER DEFAULT 0, created_by TEXT,
            created_at INTEGER NOT NULL, started_at INTEGER, completed_at INTEGER,
            workspace_kind TEXT NOT NULL DEFAULT 'scratch', workspace_path TEXT,
            claim_lock TEXT, claim_expires INTEGER
        );
        CREATE TABLE task_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL,
            kind TEXT NOT NULL, payload TEXT, created_at INTEGER NOT NULL
        );
        INSERT INTO tasks (id, title, assignee, status, created_at)
        VALUES ('legacy', 'Existing board work', 'builder', 'ready', 1);
        """
    )
    raw.commit()
    raw.close()
    kb._INITIALIZED_PATHS.discard(str(path.resolve()))

    with kbc.connect_closing(path) as conn:
        task = kb.get_task(conn, "legacy")
        assert task is not None
        assert task.review_policy == "none"
        assert task.reviewer_profile is None
        assert task.review_verdict is None
        assert kb.complete_task(conn, "legacy", summary="legacy path remains valid")


def test_explicit_no_review_material_task_keeps_existing_completion_contract(board) -> None:
    task_id = kb.create_task(
        board,
        title="Material change explicitly exempted by operator policy",
        assignee="builder",
        task_type="implementation",
        risk_level="material",
        review_policy="none",
    )
    claimed = kb.claim_task(board, task_id)
    assert claimed is not None
    assert kb.complete_task(
        board,
        task_id,
        summary="completed under explicit no-review policy",
        expected_run_id=claimed.current_run_id,
    )
    assert kb.get_task(board, task_id).status == "done"


@pytest.mark.parametrize(
    "locked_by",
    ["running", "review", "implementer_profile", "review_verdict"],
)
@pytest.mark.parametrize(
    ("new_policy", "new_reviewer"),
    [("none", None), ("required", None)],
    ids=["required-to-none", "clear-reviewer-identity"],
)
def test_review_contract_cannot_be_downgraded_or_cleared_after_work_starts(
    board,
    locked_by: str,
    new_policy: str,
    new_reviewer: str | None,
) -> None:
    task_id = _required_task(board)
    if locked_by in {"running", "review"}:
        implementation = kb.claim_task(board, task_id, claimer="builder:implementation")
        assert implementation is not None
        if locked_by == "review":
            assert kb.request_review(
                board,
                task_id,
                summary="ready",
                expected_run_id=implementation.current_run_id,
            )
    else:
        with kb.write_txn(board):
            board.execute(
                f"UPDATE tasks SET {locked_by} = ? WHERE id = ?",
                (
                    "builder" if locked_by == "implementer_profile" else "changes_requested",
                    task_id,
                ),
            )

    before = _review_mutation_snapshot(board, task_id)
    with pytest.raises(kb.ReviewGateError, match="review contract is locked"):
        kb.set_review_policy(
            board,
            task_id,
            review_policy=new_policy,
            reviewer_profile=new_reviewer,
        )

    assert _review_mutation_snapshot(board, task_id) == before


@pytest.mark.parametrize("claim_review", [False, True], ids=["parked", "missing-expected-run-id"])
def test_required_approval_requires_claimed_review_run_and_expected_run_id(
    board,
    claim_review: bool,
) -> None:
    task_id = _required_task(board)
    implementation = kb.claim_task(board, task_id, claimer="builder:implementation")
    assert implementation is not None
    assert kb.request_review(
        board,
        task_id,
        summary="ready",
        expected_run_id=implementation.current_run_id,
    )
    if claim_review:
        assert kb.claim_review_task(board, task_id, claimer="reviewer:independent") is not None

    before = _review_mutation_snapshot(board, task_id)
    with pytest.raises(kb.ReviewGateError, match="claimed review run.*expected_run_id"):
        kb.complete_task(
            board,
            task_id,
            summary="caller-supplied manual approval",
            review_verdict="approve",
            reviewer_profile="code-reviewer",
        )

    assert _review_mutation_snapshot(board, task_id) == before


def test_required_review_without_named_reviewer_fails_closed_with_remediation(board) -> None:
    task_id = _required_task(board, reviewer=None)
    claimed = kb.claim_task(board, task_id)
    assert claimed is not None

    ok, reason = kb.request_review(
        board,
        task_id,
        summary="ready",
        expected_run_id=claimed.current_run_id,
        with_reason=True,
    )

    assert (ok, reason) == (False, MISSING_REVIEWER)
    assert kb.get_task(board, task_id).status == "running"


def test_required_review_denies_self_review_with_exact_remediation(board) -> None:
    task_id = _required_task(board, reviewer="builder")
    claimed = kb.claim_task(board, task_id)
    assert claimed is not None

    ok, reason = kb.request_review(
        board,
        task_id,
        summary="ready",
        expected_run_id=claimed.current_run_id,
        with_reason=True,
    )

    assert (ok, reason) == (False, SELF_REVIEW)
    assert kb.get_task(board, task_id).status == "running"


def test_required_review_cannot_complete_without_explicit_approve_verdict(board) -> None:
    task_id = _required_task(board)
    _implementation, review = _request_and_claim_review(board, task_id)

    with pytest.raises(kb.ReviewGateError, match="^" + MISSING_VERDICT.replace("(", "\\(").replace(")", "\\)").replace(".", "\\.") + "$"):
        kb.complete_task(
            board,
            task_id,
            summary="looks good",
            expected_run_id=review.current_run_id,
        )

    assert kb.get_task(board, task_id).status == "running"


def test_independent_eligible_reviewer_approve_verdict_completes(board) -> None:
    task_id = _required_task(board)
    _implementation, review = _request_and_claim_review(board, task_id)

    assert kb.complete_task(
        board,
        task_id,
        summary="Approved after running the focused suite.",
        metadata={"reviewer_checks": ["scripts/run_tests.sh tests/hermes_cli/test_feature.py"]},
        expected_run_id=review.current_run_id,
        review_verdict="approve",
        reviewer_profile="code-reviewer",
    )

    completed = kb.get_task(board, task_id)
    assert completed is not None
    assert completed.status == "done"
    assert completed.implementer_profile == "builder"
    assert completed.reviewer_profile == "code-reviewer"
    assert completed.review_verdict == "approved"
    assert completed.reviewed_by == "code-reviewer"
    assert completed.reviewed_at is not None
    events = kb.list_events(board, task_id)
    approval = [event for event in events if event.kind == "review_approved"][-1]
    assert approval.run_id == review.current_run_id
    assert approval.payload == {
        "implementer": "builder",
        "reviewer": "code-reviewer",
        "verdict": "approved",
    }


def test_request_changes_records_non_accepting_verdict_and_returns_owner(board) -> None:
    task_id = _required_task(board)
    _implementation, review = _request_and_claim_review(board, task_id)

    assert kb.request_changes(
        board,
        task_id,
        reason="Add a migration regression.",
        expected_run_id=review.current_run_id,
    ) == (True, "builder")

    task = kb.get_task(board, task_id)
    assert task is not None
    assert task.status == "ready"
    assert task.assignee == "builder"
    assert task.review_verdict == "changes_requested"
    assert task.reviewed_by == "code-reviewer"


def test_review_escalation_is_non_accepting(board) -> None:
    task_id = _required_task(board)
    _implementation, review = _request_and_claim_review(board, task_id)
    assert kb.block_task(
        board,
        task_id,
        reason="Maintainer must choose a compatibility policy.",
        kind="needs_input",
        expected_run_id=review.current_run_id,
    )
    escalated = kb.get_task(board, task_id)
    assert escalated is not None
    assert escalated.status == "blocked"
    assert escalated.review_verdict == "escalated"

    with pytest.raises(kb.ReviewGateError, match="approved review verdict"):
        kb.complete_task(
            board,
            task_id,
            summary="escalation is not approval",
            review_verdict="approve",
            reviewer_profile="code-reviewer",
        )
    assert kb.get_task(board, task_id).status == "blocked"


def test_active_run_profile_prevents_model_or_fallback_provenance_spoof(board) -> None:
    task_id = _required_task(board)
    _implementation, review = _request_and_claim_review(board, task_id)
    with kb.write_txn(board):
        board.execute(
            "UPDATE task_runs SET profile = 'builder', metadata = ? WHERE id = ?",
            (json.dumps({"fallback_profile": "code-reviewer", "model": "review-model"}), review.current_run_id),
        )

    with pytest.raises(kb.ReviewGateError, match="active review run belongs to profile 'builder'"):
        kb.complete_task(
            board,
            task_id,
            summary="spoofed fallback approval",
            expected_run_id=review.current_run_id,
            review_verdict="approve",
            reviewer_profile="code-reviewer",
        )
    assert kb.get_task(board, task_id).status == "running"


def _fake_aux_response(content: str):
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = content
    return response


def test_auto_decomposition_structurally_marks_material_work_for_specialist_review(
    board,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root_id = kb.create_task(board, title="Ship risky backend feature", triage=True)
    payload = json.dumps(
        {
            "fanout": True,
            "rationale": "split implementation risks",
            "tasks": [
                {
                    "title": "Implement API",
                    "body": "Change the endpoint.",
                    "assignee": "builder",
                    "parents": [],
                    "task_type": "implementation",
                    "risk": "material",
                    "review_policy": "required",
                },
                {
                    "title": "Harden authentication",
                    "body": "Change auth checks.",
                    "assignee": "builder",
                    "parents": [],
                    "task_type": "implementation",
                    "risk": "security",
                    "review_policy": "required",
                },
                {
                    "title": "Refactor service boundary",
                    "body": "Change module ownership.",
                    "assignee": "builder",
                    "parents": [],
                    "task_type": "architecture",
                    "risk": "architecture",
                    "review_policy": "required",
                },
            ],
        }
    )
    profiles = [
        MagicMock(name=name, description=f"{name} role")
        for name in ("builder", "code-reviewer", "security-reviewer", "architecture-reviewer", "reviewer")
    ]
    for profile, name in zip(profiles, ("builder", "code-reviewer", "security-reviewer", "architecture-reviewer", "reviewer")):
        profile.name = name
        profile.description = f"{name} role"

    monkeypatch.setattr(decomp.profiles_mod, "list_profiles", lambda: profiles)
    monkeypatch.setattr(decomp.profiles_mod, "profile_exists", lambda name: name in {p.name for p in profiles})
    monkeypatch.setattr(decomp.profiles_mod, "get_active_profile_name", lambda: "builder")
    monkeypatch.setattr(decomp, "_load_config", lambda: {"kanban": {"default_assignee": "builder"}})
    with patch("agent.auxiliary_client.call_llm", return_value=_fake_aux_response(payload)):
        outcome = decomp.decompose_task(root_id, author="auto-decomposer")

    assert outcome.ok, outcome.reason
    children = [kb.get_task(board, task_id) for task_id in outcome.child_ids or []]
    assert [(task.review_policy, task.reviewer_profile) for task in children] == [
        ("required", "code-reviewer"),
        ("required", "security-reviewer"),
        ("required", "architecture-reviewer"),
    ]
    assert all(task.review_verdict is None for task in children)


def test_manual_decomposition_explicit_reviewer_overrides_policy_selection(
    board,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root_id = kb.create_task(board, title="Manual decomposition", triage=True)
    payload = json.dumps(
        {
            "fanout": True,
            "rationale": "one implementation child",
            "tasks": [
                {
                    "title": "Implement worker",
                    "assignee": "builder",
                    "parents": [],
                    "task_type": "implementation",
                    "risk": "material",
                    "review_policy": "required",
                }
            ],
        }
    )
    profiles = []
    for name in ("builder", "code-reviewer", "reviewer"):
        profile = MagicMock()
        profile.name = name
        profile.description = name
        profiles.append(profile)
    monkeypatch.setattr(decomp.profiles_mod, "list_profiles", lambda: profiles)
    monkeypatch.setattr(decomp.profiles_mod, "profile_exists", lambda name: name in {p.name for p in profiles})
    monkeypatch.setattr(decomp.profiles_mod, "get_active_profile_name", lambda: "builder")
    monkeypatch.setattr(decomp, "_load_config", lambda: {"kanban": {"default_assignee": "builder"}})
    with patch("agent.auxiliary_client.call_llm", return_value=_fake_aux_response(payload)):
        outcome = decomp.decompose_task(root_id, author="operator", reviewer="reviewer")

    assert outcome.ok, outcome.reason
    child = kb.get_task(board, (outcome.child_ids or [])[0])
    assert child is not None
    assert child.review_policy == "required"
    assert child.reviewer_profile == "reviewer"


def test_cli_create_and_show_expose_explicit_review_contract(board) -> None:
    output = kanban_cli.run_slash(
        "create 'CLI material change' --assignee builder --task-type implementation "
        "--risk material --review-policy required --reviewer code-reviewer --json"
    )
    task = json.loads(output)
    assert task["review_policy"] == "required"
    assert task["reviewer_profile"] == "code-reviewer"
    shown = json.loads(kanban_cli.run_slash(f"show {task['id']} --json"))["task"]
    assert shown["task_type"] == "implementation"
    assert shown["risk_level"] == "material"


def test_reviewer_tool_records_explicit_approve_without_trusting_model_metadata(
    board,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tools import kanban_tools

    task_id = _required_task(board)
    _implementation, review = _request_and_claim_review(board, task_id)
    monkeypatch.setenv("HERMES_KANBAN_TASK", task_id)
    monkeypatch.setenv("HERMES_KANBAN_RUN_ID", str(review.current_run_id))
    monkeypatch.setenv("HERMES_PROFILE", "code-reviewer")

    result = json.loads(
        kanban_tools._handle_complete(
            {
                "summary": "Approved through the reviewer worker tool.",
                "review_verdict": "approve",
                "metadata": {"model": "same-model-is-not-profile-identity"},
            }
        )
    )

    assert result["ok"] is True
    assert kb.get_task(board, task_id).reviewed_by == "code-reviewer"
