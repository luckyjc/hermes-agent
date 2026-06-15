"""Document extraction tools backed by the local doc-tools sidecar."""

from __future__ import annotations

import json
import os
import shutil
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

from tools.registry import registry, tool_error, tool_result

DEFAULT_BASE_URL = "http://127.0.0.1:9478"
DEFAULT_STACK_DIR = Path.home() / "docker" / "doc-tools"
DEFAULT_TIMEOUT = 120.0


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _config() -> dict[str, Any]:
    stack_dir = Path(
        os.path.expandvars(
            os.path.expanduser(os.getenv("HERMES_DOC_TOOLS_STACK_DIR", str(DEFAULT_STACK_DIR)))
        )
    ).resolve()
    intake_override = os.getenv("HERMES_DOC_TOOLS_INTAKE_DIR", "").strip()
    intake_dir = (
        Path(os.path.expandvars(os.path.expanduser(intake_override))).resolve()
        if intake_override
        else (stack_dir / "intake").resolve()
    )
    timeout_raw = os.getenv("HERMES_DOC_TOOLS_TIMEOUT", str(DEFAULT_TIMEOUT)).strip()
    try:
        timeout = float(timeout_raw)
    except ValueError:
        timeout = DEFAULT_TIMEOUT
    if timeout <= 0:
        timeout = DEFAULT_TIMEOUT
    return {
        "base_url": os.getenv("HERMES_DOC_TOOLS_BASE_URL", DEFAULT_BASE_URL).strip().rstrip("/"),
        "stack_dir": stack_dir,
        "intake_dir": intake_dir,
        "timeout": timeout,
    }


def check_document_tools_requirements() -> bool:
    cfg = _config()
    return bool(cfg["base_url"]) and cfg["intake_dir"].exists()


def _container_intake_path(staged_path: Path, intake_dir: Path) -> str:
    relative = staged_path.resolve().relative_to(intake_dir.resolve())
    return f"/data/intake/{relative.as_posix()}"


def _stage_file(path: Path, intake_dir: Path) -> tuple[Path, bool]:
    resolved = path.expanduser().resolve()
    intake_dir.mkdir(parents=True, exist_ok=True)
    try:
        resolved.relative_to(intake_dir.resolve())
        return resolved, False
    except ValueError:
        pass
    staged_name = f"{resolved.stem[:40]}-{uuid.uuid4().hex}{resolved.suffix}"
    staged_path = intake_dir / staged_name
    shutil.copy2(resolved, staged_path)
    return staged_path, True


def document_extract(
    path: str,
    *,
    backend: str = "auto",
    mode: str = "markdown",
    ocr: bool = False,
    structured: bool = False,
    extract_tables: bool = False,
    metadata_only: bool = False,
    max_chars: int | None = 200_000,
) -> str:
    if not path:
        return tool_error("Missing required parameter 'path'")
    resolved = Path(path).expanduser().resolve()
    if not resolved.exists():
        return tool_error(f"Document not found: {resolved}")
    if not resolved.is_file():
        return tool_error(f"Document path is not a file: {resolved}")
    if backend not in {"auto", "markitdown", "docling"}:
        return tool_error("backend must be one of: auto, markitdown, docling")
    if mode not in {"markdown", "structured"}:
        return tool_error("mode must be one of: markdown, structured")

    cfg = _config()
    staged_path: Path | None = None
    copied = False
    try:
        staged_path, copied = _stage_file(resolved, cfg["intake_dir"])
        payload = {
            "source": _container_intake_path(staged_path, cfg["intake_dir"]),
            "source_kind": "local_path",
            "backend": backend,
            "mode": mode,
            "ocr": bool(ocr),
            "structured": bool(structured),
            "extract_tables": bool(extract_tables),
            "metadata_only": bool(metadata_only),
            "max_chars": max_chars,
        }
        request = urllib.request.Request(
            f"{cfg['base_url']}/extract",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=cfg["timeout"]) as response:
            result = json.loads(response.read().decode("utf-8"))
        result["original_source"] = str(resolved)
        result["staged_source"] = str(staged_path)
        result["cleanup_performed"] = bool(copied)
        return tool_result(result)
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read().decode("utf-8")
        except Exception:
            body = str(exc)
        return tool_error(f"doc-tools request failed: {body}", status_code=exc.code)
    except Exception as exc:
        return tool_error(str(exc))
    finally:
        if copied and staged_path is not None and staged_path.exists():
            try:
                staged_path.unlink()
            except OSError:
                pass


def document_tools_health() -> str:
    cfg = _config()
    result: dict[str, Any] = {
        "base_url": cfg["base_url"],
        "stack_dir_exists": cfg["stack_dir"].exists(),
        "intake_dir_exists": cfg["intake_dir"].exists(),
    }
    try:
        request = urllib.request.Request(f"{cfg['base_url']}/health", method="GET")
        with urllib.request.urlopen(request, timeout=min(cfg["timeout"], 10.0)) as response:
            body = response.read().decode("utf-8")
            result["http_status"] = response.status
            try:
                result["health"] = json.loads(body)
            except json.JSONDecodeError:
                result["health_text"] = body[:1000]
    except Exception as exc:
        result["error"] = str(exc)
    return tool_result(result)


DOCUMENT_EXTRACT_SCHEMA = {
    "name": "document_extract",
    "description": "Extract Markdown or structured content from a local document using the local doc-tools sidecar. The file is staged into the sidecar intake directory when needed.",
    "parameters": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Local path to the document/file to extract."},
            "backend": {"type": "string", "enum": ["auto", "markitdown", "docling"], "default": "auto"},
            "mode": {"type": "string", "enum": ["markdown", "structured"], "default": "markdown"},
            "ocr": {"type": "boolean", "default": False},
            "structured": {"type": "boolean", "default": False},
            "extract_tables": {"type": "boolean", "default": False},
            "metadata_only": {"type": "boolean", "default": False},
            "max_chars": {"type": ["integer", "null"], "default": 200000},
        },
        "required": ["path"],
    },
}

DOCUMENT_HEALTH_SCHEMA = {
    "name": "document_tools_health",
    "description": "Check whether the local doc-tools sidecar and intake directory are reachable without extracting private document content.",
    "parameters": {"type": "object", "properties": {}},
}


registry.register(
    name="document_extract",
    toolset="document",
    schema=DOCUMENT_EXTRACT_SCHEMA,
    handler=lambda args, **kw: document_extract(
        args.get("path", ""),
        backend=args.get("backend", "auto"),
        mode=args.get("mode", "markdown"),
        ocr=bool(args.get("ocr", False)),
        structured=bool(args.get("structured", False)),
        extract_tables=bool(args.get("extract_tables", False)),
        metadata_only=bool(args.get("metadata_only", False)),
        max_chars=args.get("max_chars", 200_000),
    ),
    check_fn=check_document_tools_requirements,
    emoji="📄",
)

registry.register(
    name="document_tools_health",
    toolset="document",
    schema=DOCUMENT_HEALTH_SCHEMA,
    handler=lambda args, **kw: document_tools_health(),
    check_fn=check_document_tools_requirements,
    emoji="📄",
)
