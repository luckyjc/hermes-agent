from __future__ import annotations

import importlib.util
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SKILL_ROOT = ROOT / "skills" / "workflow" / "session-handoff"
BUILD_SCRIPT = SKILL_ROOT / "scripts" / "build_session_handoff.py"
CONTINUE_SCRIPT = SKILL_ROOT / "scripts" / "session_handoff_continue.py"


def load_builder():
    spec = importlib.util.spec_from_file_location("build_session_handoff", BUILD_SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_discovers_project_scaffolding_files(tmp_path: Path) -> None:
    builder = load_builder()
    for relative in ("AGENTS.md", ".hermes/bootstrap.md", "docs/CURRENT_STATE.md"):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("context\n", encoding="utf-8")

    assert builder.discover_context(tmp_path) == [
        "AGENTS.md",
        ".hermes/bootstrap.md",
        "docs/CURRENT_STATE.md",
    ]


def test_finalize_writes_canonical_and_persistent_archive(tmp_path: Path) -> None:
    builder = load_builder()
    body = tmp_path / "draft.md"
    body.write_text("SESSION HANDOFF\n\nGoal:\n- Continue the idea.\n", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("context\n", encoding="utf-8")
    canonical = tmp_path / "canonical" / "NEXT_SESSION.md"
    archive_dir = tmp_path / "archive"

    canonical_result, archive, count = builder.finalize(
        body,
        tmp_path,
        canonical,
        archive_dir,
        1200,
    )

    assert canonical_result == canonical
    assert archive.parent == archive_dir
    assert count == 7
    assert canonical.read_text(encoding="utf-8") == archive.read_text(encoding="utf-8")
    rendered = canonical.read_text(encoding="utf-8")
    assert rendered.startswith("SESSION HANDOFF\n\nDeterministic provenance:")
    assert f"`{tmp_path / 'AGENTS.md'}`" in rendered
    assert "Goal:\n- Continue the idea." in rendered


def test_finalize_rejects_oversized_body(tmp_path: Path) -> None:
    builder = load_builder()
    body = tmp_path / "draft.md"
    body.write_text("SESSION HANDOFF\n" + "word " * 10, encoding="utf-8")

    with pytest.raises(ValueError, match="maximum is 5"):
        builder.finalize(body, tmp_path, tmp_path / "next.md", tmp_path / "archive", 5)


def test_render_metadata_is_counts_only_for_dirty_state(tmp_path: Path, monkeypatch) -> None:
    builder = load_builder()

    def fake_git(root: Path, *args: str) -> str:
        if args == ("branch", "--show-current"):
            return "main"
        if args == ("status", "--short"):
            return " M secret-client-name.txt\n?? private-transcript.md"
        return ""

    monkeypatch.setattr(builder, "run_git", fake_git)
    rendered = builder.render_metadata(tmp_path, datetime(2026, 1, 1, tzinfo=timezone.utc))

    assert "dirty (2 paths)" in rendered
    assert "secret-client-name" not in rendered
    assert "private-transcript" not in rendered


def test_manual_mode_does_not_require_launcher(tmp_path: Path) -> None:
    handoff = tmp_path / "NEXT_SESSION.md"
    handoff.write_text("SESSION HANDOFF\n\nGoal:\n- Continue.\n", encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(CONTINUE_SCRIPT),
            str(handoff),
            "--manual",
            "--launcher",
            "definitely-not-installed",
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    assert result.returncode == 0
    assert f"handoff_file={handoff}" in result.stdout
    assert result.stderr == ""
