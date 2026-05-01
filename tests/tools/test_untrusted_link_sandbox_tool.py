import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools import untrusted_link_sandbox_tool as tool


def make_sandbox(tmp_path: Path) -> Path:
    root = tmp_path / "sandbox"
    (root / "bin").mkdir(parents=True)
    (root / "reports").mkdir()
    (root / "quarantine" / "downloads").mkdir(parents=True)
    (root / "docker-compose.yml").write_text("services: {}\n")
    triage = root / "bin" / "triage"
    triage.write_text("#!/usr/bin/env bash\n")
    triage.chmod(0o755)
    return root


def test_tool_available_with_expected_stack(monkeypatch, tmp_path):
    root = make_sandbox(tmp_path)
    monkeypatch.setenv("HERMES_UNTRUSTED_LINK_SANDBOX_DIR", str(root))

    assert tool._tool_available() is True


def test_host_quarantine_path_is_converted(monkeypatch, tmp_path):
    root = make_sandbox(tmp_path)
    target = root / "quarantine" / "downloads" / "sample.txt"
    target.write_text("hello")
    monkeypatch.setenv("HERMES_UNTRUSTED_LINK_SANDBOX_DIR", str(root))

    assert tool._containerish_target(str(target)) == "/quarantine/downloads/sample.txt"


def test_triage_invokes_wrapper_and_reads_summary(monkeypatch, tmp_path):
    root = make_sandbox(tmp_path)
    report = root / "reports" / "run.md"
    summary = root / "reports" / "run.json"
    report.write_text("# Report\n\nUseful excerpt\n")
    summary.write_text(json.dumps({"target": "https://example.com", "type": "url", "report_path": "/reports/run.md"}))
    monkeypatch.setenv("HERMES_UNTRUSTED_LINK_SANDBOX_DIR", str(root))

    captured = {}

    def fake_run(args, **kwargs):
        captured["args"] = args
        captured["cwd"] = kwargs["cwd"]
        return SimpleNamespace(returncode=0, stdout="/reports/run.md\n", stderr="")

    monkeypatch.setattr(tool.subprocess, "run", fake_run)

    result = json.loads(tool.untrusted_link_triage("https://example.com", deep=True))

    assert captured["args"] == ["./bin/triage", "--deep", "https://example.com"]
    assert captured["cwd"] == str(root)
    assert result["success"] is True
    assert result["report_path_host"] == str(report)
    assert result["summary"]["type"] == "url"
    assert result["summary"]["report_path_host"] == str(report)
    assert "Useful excerpt" in result["report_excerpt"]


def test_audit_repo_wrapper(monkeypatch, tmp_path):
    root = make_sandbox(tmp_path)
    monkeypatch.setenv("HERMES_UNTRUSTED_LINK_SANDBOX_DIR", str(root))
    captured = {}

    def fake_run(args, **kwargs):
        captured["args"] = args
        return SimpleNamespace(returncode=0, stdout="/reports/repo.md\n", stderr="")

    monkeypatch.setattr(tool.subprocess, "run", fake_run)

    result = json.loads(tool.audit_untrusted_repo("https://github.com/octocat/Hello-World"))

    assert captured["args"] == ["./bin/audit-repo", "https://github.com/octocat/Hello-World"]
    assert result["success"] is True


def test_inspect_download_converts_host_path(monkeypatch, tmp_path):
    root = make_sandbox(tmp_path)
    target = root / "quarantine" / "downloads" / "sample.txt"
    target.write_text("hello")
    monkeypatch.setenv("HERMES_UNTRUSTED_LINK_SANDBOX_DIR", str(root))
    captured = {}

    def fake_run(args, **kwargs):
        captured["args"] = args
        return SimpleNamespace(returncode=0, stdout="/reports/download.md\n", stderr="")

    monkeypatch.setattr(tool.subprocess, "run", fake_run)

    json.loads(tool.inspect_untrusted_download(str(target)))

    assert captured["args"] == ["./bin/inspect-download", "/quarantine/downloads/sample.txt"]
