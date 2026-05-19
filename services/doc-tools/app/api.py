from __future__ import annotations

import mimetypes
import time

from fastapi import APIRouter, HTTPException

from backends import DoclingBackend, MarkItDownBackend
from config import get_settings
from heuristics import choose_backend
from models import ErrorInfo, ExtractRequest, ExtractResponse, HealthResponse
from security import FileTooLargeError, SecurityError, validate_source_path

router = APIRouter()

BACKENDS = {
    "markitdown": MarkItDownBackend(),
    "docling": DoclingBackend(),
}


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(backends={name: True for name in BACKENDS})


@router.post("/extract", response_model=ExtractResponse)
def extract(request: ExtractRequest) -> ExtractResponse:
    settings = get_settings()

    if request.source_kind == "url":
        return ExtractResponse(
            ok=False,
            source=request.source,
            source_kind=request.source_kind,
            warnings=["URL handling is not implemented in v1 of doc-tools"],
            error=ErrorInfo(
                code="url_not_supported_yet",
                message="Use Hermes web_extract for URLs in v1",
            ),
        )

    try:
        source_path = validate_source_path(request.source, settings)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=ErrorInfo(code="source_not_found", message=str(exc)).model_dump(),
        ) from exc
    except SecurityError as exc:
        raise HTTPException(
            status_code=403,
            detail=ErrorInfo(code="path_not_allowed", message=str(exc)).model_dump(),
        ) from exc
    except FileTooLargeError as exc:
        raise HTTPException(
            status_code=413,
            detail=ErrorInfo(code="file_too_large", message=str(exc)).model_dump(),
        ) from exc

    primary_backend, fallback_chain = choose_backend(request)
    warnings: list[str] = []
    metadata: dict = {}
    markdown = ""
    backend_used: str | None = None
    last_error: Exception | None = None

    started = time.perf_counter()
    for candidate in fallback_chain:
        backend = BACKENDS[candidate]
        try:
            markdown, metadata = backend.extract(source_path, request)
            backend_used = candidate
            if candidate != primary_backend:
                warnings.append(
                    f"Primary backend {primary_backend} failed; used fallback {candidate}"
                )
            break
        except Exception as exc:  # pragma: no cover
            last_error = exc
            warnings.append(f"{candidate} failed: {exc}")

    elapsed_ms = int((time.perf_counter() - started) * 1000)

    if backend_used is None:
        raise HTTPException(
            status_code=500,
            detail=ErrorInfo(
                code="backend_failed",
                message=str(last_error) if last_error else "All backends failed",
            ).model_dump(),
        )

    structured_data = metadata.pop("structured_data", None)
    mime_type = mimetypes.guess_type(str(source_path))[0] or "application/octet-stream"

    return ExtractResponse(
        ok=True,
        backend_used=backend_used,
        source=str(source_path),
        source_kind="local_path",
        mime_type=mime_type,
        markdown=markdown,
        structured_data=structured_data,
        metadata=metadata,
        warnings=warnings,
        fallback_chain=fallback_chain,
        timings_ms={"total": elapsed_ms},
    )
