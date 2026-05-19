from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    ok: bool = True
    service: str = "doc-tools"
    version: str = "0.1.0"
    backends: dict[str, bool]


class ExtractRequest(BaseModel):
    source: str
    source_kind: Literal["auto", "local_path", "url"] = "auto"
    backend: Literal["auto", "markitdown", "docling"] = "auto"
    mode: Literal["markdown", "structured"] = "markdown"
    ocr: bool = False
    structured: bool = False
    extract_tables: bool = False
    metadata_only: bool = False
    max_chars: int | None = Field(default=200_000, ge=1)


class ErrorInfo(BaseModel):
    code: str
    message: str


class ExtractResponse(BaseModel):
    ok: bool
    backend_used: str | None = None
    source: str | None = None
    source_kind: str | None = None
    mime_type: str | None = None
    markdown: str | None = None
    structured_data: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    fallback_chain: list[str] = Field(default_factory=list)
    timings_ms: dict[str, int] = Field(default_factory=dict)
    error: ErrorInfo | None = None
