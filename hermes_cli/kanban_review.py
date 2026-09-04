"""Explicit Kanban review-policy validation and reviewer selection.

The persisted task row owns policy and profile identity. Model/provider/fallback
metadata is deliberately ignored: an independent review is a different Hermes
profile, not merely a different model invocation.
"""
from __future__ import annotations

from collections.abc import Callable, Collection
from typing import Optional

VALID_REVIEW_POLICIES = frozenset({"none", "required"})
VALID_TASK_TYPES = frozenset(
    {"implementation", "architecture", "security", "research", "documentation", "operations", "other"}
)
VALID_RISK_LEVELS = frozenset({"low", "material", "security", "architecture"})
VALID_REVIEW_VERDICTS = frozenset({"pending", "approved", "changes_requested", "escalated"})
APPROVE_INPUT = "approve"

MISSING_REVIEWER_REMEDIATION = (
    "review required: name an eligible reviewer profile different from the implementer "
    "with reviewer=<profile> (CLI: --reviewer <profile>)"
)


class ReviewGateError(ValueError):
    """A required review transition failed without mutating task state."""


def normalize_choice(value: Optional[str], *, field: str, allowed: Collection[str], default: str) -> str:
    normalized = str(value or default).strip().lower().replace("_", "-")
    if normalized not in allowed:
        raise ValueError(f"{field} must be one of {sorted(allowed)}, got {value!r}")
    return normalized


def normalize_review_policy(value: Optional[str]) -> str:
    return normalize_choice(value, field="review_policy", allowed=VALID_REVIEW_POLICIES, default="none")


def normalize_task_type(value: Optional[str]) -> str:
    return normalize_choice(value, field="task_type", allowed=VALID_TASK_TYPES, default="other")


def normalize_risk_level(value: Optional[str]) -> str:
    return normalize_choice(value, field="risk_level", allowed=VALID_RISK_LEVELS, default="low")


def reviewer_preferences(task_type: str, risk_level: str) -> tuple[str, ...]:
    """Role order for auto-decomposed review-required work."""
    if risk_level == "security" or task_type == "security":
        return ("security-reviewer", "code-reviewer", "reviewer")
    if risk_level == "architecture" or task_type == "architecture":
        return ("architecture-reviewer", "code-reviewer", "reviewer")
    if task_type == "implementation" or risk_level == "material":
        return ("code-reviewer", "reviewer")
    return ("reviewer",)


def select_reviewer(
    *,
    task_type: str,
    risk_level: str,
    implementer: Optional[str],
    available_profiles: Collection[str],
    explicit_reviewer: Optional[str] = None,
) -> str:
    """Select a named profile while never silently selecting the implementer.

    An explicit manual reviewer must exist in the supplied roster. Automatic
    selection prefers an installed role profile; if no role is installed, the
    primary policy role remains explicit so dispatch fails visibly instead of
    falling back to the implementer's profile.
    """
    available = set(available_profiles)
    if explicit_reviewer:
        reviewer = explicit_reviewer.strip().lower()
        if reviewer not in available:
            raise ReviewGateError(
                f"reviewer profile {reviewer!r} is not eligible because it does not exist; "
                f"create it with `hermes profile create {reviewer}` or pass --reviewer <existing-profile>"
            )
        if reviewer == implementer:
            raise ReviewGateError(self_review_remediation(reviewer, implementer))
        return reviewer

    preferences = reviewer_preferences(task_type, risk_level)
    for reviewer in preferences:
        if reviewer in available and reviewer != implementer:
            return reviewer
    return next((reviewer for reviewer in preferences if reviewer != implementer), preferences[0])


def self_review_remediation(reviewer: str, implementer: Optional[str]) -> str:
    return (
        f"independent review required: reviewer profile {reviewer!r} matches implementer profile "
        f"{implementer!r}; choose a different eligible reviewer with reviewer=<profile> "
        "(CLI: --reviewer <profile>)"
    )


def ineligible_reviewer_remediation(reviewer: str) -> str:
    return (
        f"review required: reviewer profile {reviewer!r} is not eligible because it does not exist; "
        f"create it with `hermes profile create {reviewer}` or choose an existing profile with "
        "reviewer=<profile> (CLI: --reviewer <profile>)"
    )


def validate_required_reviewer(
    *,
    reviewer: Optional[str],
    implementer: Optional[str],
    profile_exists: Callable[[str], bool],
) -> str:
    if not reviewer:
        raise ReviewGateError(MISSING_REVIEWER_REMEDIATION)
    if not implementer:
        raise ReviewGateError(
            "review required: implementer profile provenance is missing; assign the task to a named "
            "implementer profile, rerun the implementation, then request review"
        )
    if reviewer == implementer:
        raise ReviewGateError(self_review_remediation(reviewer, implementer))
    try:
        eligible = bool(profile_exists(reviewer))
    except Exception:
        eligible = False
    if not eligible:
        raise ReviewGateError(ineligible_reviewer_remediation(reviewer))
    return reviewer


def validate_review_contract_change(
    *,
    status: str,
    current_policy: str,
    current_reviewer: Optional[str],
    target_policy: str,
    target_reviewer: Optional[str],
    has_implementer: bool,
    review_verdict: Optional[str],
    has_review_provenance: bool,
) -> bool:
    """Return whether the contract changed, rejecting destructive locked changes."""
    contract_changed = (
        target_policy != current_policy or target_reviewer != current_reviewer
    )
    contract_locked = (
        status in {"running", "review"}
        or has_implementer
        or review_verdict is not None
    )
    clears_required_policy = current_policy == "required" and target_policy == "none"
    clears_reviewer_identity = current_reviewer is not None and target_reviewer is None
    clears_review_provenance = contract_changed and has_review_provenance
    if contract_locked and (
        clears_required_policy or clears_reviewer_identity or clears_review_provenance
    ):
        raise ReviewGateError(
            "review contract is locked after work starts or review provenance exists; "
            "required policy and reviewer identity cannot be cleared"
        )
    return contract_changed


def missing_verdict_remediation(reviewer: Optional[str]) -> str:
    return (
        "review required: task cannot complete without review_verdict='approve' from reviewer "
        f"{reviewer!r}; claim the review as that profile and call "
        "kanban_complete(..., review_verdict='approve')"
    )


def active_review_run_remediation(reviewer: Optional[str]) -> str:
    return (
        "review required: approval must come from a claimed review run for reviewer "
        f"{reviewer!r} and include that run's expected_run_id; claim the review as that "
        "profile and retry"
    )


def non_accepting_verdict_remediation(verdict: Optional[str], reviewer: Optional[str]) -> str:
    return (
        "review required: task has no approved review verdict "
        f"(current verdict: {verdict!r}); return it to review and obtain "
        f"review_verdict='approve' from eligible reviewer {reviewer!r}"
    )
