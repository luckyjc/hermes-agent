from pathlib import Path

from models import ExtractRequest

TEXTISH_EXTENSIONS = {
    ".csv",
    ".docx",
    ".html",
    ".json",
    ".md",
    ".pptx",
    ".txt",
    ".xlsx",
    ".xml",
}


def choose_backend(request: ExtractRequest) -> tuple[str, list[str]]:
    if request.backend != "auto":
        return request.backend, [request.backend]

    if request.source_kind == "url":
        return "markitdown", ["markitdown"]

    suffix = Path(request.source).suffix.lower()

    if request.mode == "structured" or request.ocr:
        return "docling", ["docling"]

    if suffix == ".pdf":
        return "markitdown", ["markitdown", "docling"]

    if suffix in TEXTISH_EXTENSIONS:
        return "markitdown", ["markitdown"]

    return "markitdown", ["markitdown"]
