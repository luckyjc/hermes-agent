from __future__ import annotations

from pathlib import Path

from models import ExtractRequest


def _apply_char_limit(content: str, max_chars: int | None) -> tuple[str, bool]:
    if max_chars is None or len(content) <= max_chars:
        return content, False

    return content[:max_chars], True


class DoclingBackend:
    name = "docling"

    def extract(self, source: Path, request: ExtractRequest) -> tuple[str, dict]:
        from docling.document_converter import DocumentConverter

        converter = DocumentConverter()
        result = converter.convert(source)
        document = result.document
        raw_markdown = document.export_to_markdown()
        markdown = "" if request.metadata_only else raw_markdown
        markdown, truncated = _apply_char_limit(markdown, request.max_chars)

        metadata = {
            "filename": source.name,
            "extension": source.suffix.lower(),
            "size_bytes": source.stat().st_size,
            "converter": self.name,
            "status": str(result.status),
            "truncated": truncated,
            "raw_markdown_chars": len(raw_markdown),
        }

        if request.mode == "structured" or request.structured:
            metadata["structured_data"] = document.export_to_dict()

        return markdown, metadata
