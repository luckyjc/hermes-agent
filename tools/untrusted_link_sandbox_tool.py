"""Tools for routing untrusted URLs/files through the local sandbox stack."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from tools.registry import registry, tool_error, tool_result

DEFAULT_STACK_DIR = Path.home() / "docker" / "untrusted-link-sandbox"
DEFAULT_TIMEOUT = 300.0


def _stack_dir() -> Path:
    return Path(
        os.path.expandvars(
            os.path.expanduser(os.getenv("HERMES_UNTRUSTED_LINK_SANDBOX_DIR", str(DEFAULT_STACK_DIR)))
        )
    ).resolve()


def _timeout() -> float:
    raw = os.getenv("HERMES_UNTRUSTED_LINK_SANDBOX_TIMEOUT", str(DEFAULT_TIMEOUT)).strip()
    try:
        value = float(raw)
    except ValueError:
        value = DEFAULT_TIMEOUT
    return value if value > 0 else DEFAULT_TIMEOUT


def check_untrusted_link_sandbox_requirements() -> bool:
    root = _stack_dir()
    return (root / "bin" / "triage").exists() and (root / "docker-compose.yml").exists()


def _safe_report_path(container_path: str | None, root: Path) -> str | None:
    if not container_path:
        return None
    if container_path.startswith("/reports/"):
        return str(root / "reports" / container_path.removeprefix("/reports/"))
    return container_path


def _latest_report_after(root: Path, before: set[Path]) -> Path | None:
    reports = sorted((root / "reports").glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for path in reports:
        if path not in before:
            return path
    return reports[0] if reports else None


def untrusted_link_triage(target: str, *, deep: bool = False, timeout: float | None = None) -> str:
    if not target:
        return tool_error("Missing required parameter 'target'")
    root = _stack_dir()
    triage = root / "bin" / "triage"
    if not triage.exists():
        return tool_error(f"Untrusted link sandbox triage command not found: {triage}")

    reports_dir = root / "reports"
    before = set(reports_dir.glob("*.json")) if reports_dir.exists() else set()
    cmd = [str(triage)]
    if deep:
        cmd.append("--deep")
    cmd.append(target)
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(root),
            text=True,
            capture_output=True,
            timeout=timeout or _timeout(),
            check=False,
        )
    except subprocess.TimeoutExpired:
        return tool_error("untrusted link sandbox triage timed out", timeout=timeout or _timeout())
    except Exception as exc:
        return tool_error(str(exc))

    latest = _latest_report_after(root, before)
    summary: dict[str, Any] = {
        "success": proc.returncode == 0,
        "returncode": proc.returncode,
        "target": target,
        "deep": bool(deep),
        "stdout_tail": proc.stdout[-4000:],
        "stderr_tail": proc.stderr[-4000:],
    }
    if latest is not None:
        summary["json_report_path"] = str(latest)
        try:
            report = json.loads(latest.read_text(encoding="utf-8", errors="replace"))
            if isinstance(report, dict):
                report = dict(report)
                if "report_path" in report:
                    report["host_report_path"] = _safe_report_path(str(report.get("report_path") or ""), root)
                summary["report"] = report
        except Exception as exc:
            summary["report_error"] = str(exc)
    return tool_result(summary)


TRIAGE_SCHEMA = {
    "name": "untrusted_link_triage",
    "description": "Inspect an untrusted URL, public repo URL, or sandbox quarantine file using the local disposable untrusted-link sandbox. Static/sandboxed by default; deep mode uses the CDP browser path for web URLs.",
    "parameters": {
        "type": "object",
        "properties": {
            "target": {"type": "string", "description": "HTTP(S) URL, GitHub/GitLab repo URL, or /quarantine/downloads|artifacts path."},
            "deep": {"type": "boolean", "default": False, "description": "Use deeper browser/CDP inspection for web URLs. Ignored for repository URLs."},
            "timeout": {"type": ["number", "null"], "default": None, "description": "Optional timeout in seconds."},
        },
        "required": ["target"],
    },
}


registry.register(
    name="untrusted_link_triage",
    toolset="untrusted_link_sandbox",
    schema=TRIAGE_SCHEMA,
    handler=lambda args, **kw: untrusted_link_triage(
        args.get("target", ""),
        deep=bool(args.get("deep", False)),
        timeout=args.get("timeout"),
    ),
    check_fn=check_untrusted_link_sandbox_requirements,
    emoji="🧪",
)
