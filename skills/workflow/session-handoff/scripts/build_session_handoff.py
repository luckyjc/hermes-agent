#!/usr/bin/env python3
"""Finalize a compact session handoff with deterministic project metadata."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

CONTEXT_CANDIDATES = (
    "AGENTS.md",
    ".hermes/bootstrap.md",
    "docs/CURRENT_STATE.md",
    "docs/TESTING.md",
    "CONTEXT.md",
    "docs/adr/README.md",
)
DEFAULT_CANONICAL = Path("/tmp/athena-session-handoffs/NEXT_SESSION.md")


def run_git(root: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(root), *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    return proc.stdout.strip() if proc.returncode == 0 else ""


def resolve_project_root(start: Path) -> Path:
    start = start.expanduser().resolve()
    root = run_git(start, "rev-parse", "--show-toplevel")
    return Path(root).resolve() if root else start


def discover_context(root: Path) -> list[str]:
    return [relative for relative in CONTEXT_CANDIDATES if (root / relative).is_file()]


def persistent_archive_dir() -> Path:
    state_home = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state"))
    profile = os.environ.get("HERMES_PROFILE", "default")
    return state_home / "hermes" / "session-handoffs" / profile


def word_count(text: str) -> int:
    return len(text.split())


def render_metadata(root: Path, created_at: datetime) -> str:
    branch = run_git(root, "branch", "--show-current") or "not-a-git-repo"
    status = run_git(root, "status", "--short")
    context_files = discover_context(root)
    status_summary = "clean" if not status else f"dirty ({len(status.splitlines())} paths)"
    context_lines = "\n".join(f"- `{root / relative}`" for relative in context_files)
    if not context_lines:
        context_lines = "- No standard project context files discovered."
    return (
        "Deterministic provenance:\n"
        f"- Created: {created_at.isoformat()}\n"
        f"- Project root: `{root}`\n"
        f"- Git branch: `{branch}`\n"
        f"- Git worktree: {status_summary}\n"
        f"- Hermes profile: `{os.environ.get('HERMES_PROFILE', 'default')}`\n\n"
        "Project context to read first:\n"
        f"{context_lines}\n"
    )


def finalize(
    body_path: Path,
    project_root: Path,
    canonical_path: Path,
    archive_dir: Path,
    max_words: int,
) -> tuple[Path, Path, int]:
    body = body_path.read_text(encoding="utf-8").strip()
    if not body.startswith("SESSION HANDOFF"):
        raise ValueError("handoff body must start with 'SESSION HANDOFF'")
    count = word_count(body)
    if count > max_words:
        raise ValueError(f"handoff body is {count} words; maximum is {max_words}")

    now = datetime.now(timezone.utc)
    first_line, _, remainder = body.partition("\n")
    final_text = f"{first_line}\n\n{render_metadata(project_root, now)}"
    if remainder.strip():
        final_text += f"\n{remainder.strip()}\n"

    canonical_path.parent.mkdir(parents=True, exist_ok=True)
    archive_dir.mkdir(parents=True, exist_ok=True)
    archive_path = archive_dir / now.strftime("session-handoff-%Y%m%d-%H%M%SZ.md")
    canonical_path.write_text(final_text, encoding="utf-8")
    archive_path.write_text(final_text, encoding="utf-8")
    return canonical_path, archive_path, count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("body_file", type=Path, help="Agent-authored compact SESSION HANDOFF body")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--canonical", type=Path, default=DEFAULT_CANONICAL)
    parser.add_argument("--archive-dir", type=Path, default=None)
    parser.add_argument("--max-words", type=int, default=1200)
    args = parser.parse_args()

    try:
        root = resolve_project_root(args.project_root)
        canonical, archive, count = finalize(
            args.body_file.expanduser().resolve(),
            root,
            args.canonical.expanduser().resolve(),
            (args.archive_dir or persistent_archive_dir()).expanduser().resolve(),
            args.max_words,
        )
    except (OSError, ValueError) as exc:
        print(f"session handoff finalize failed: {exc}", file=sys.stderr)
        return 2

    print(f"handoff_file={canonical}")
    print(f"archive_file={archive}")
    print(f"body_words={count}")
    print(f"project_root={root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
