from __future__ import annotations

from pathlib import Path

from models import ExtractRequest


def _apply_char_limit(content: str, max_chars: int | None) -> tuple[str, bool]:
    if max_chars is None or len(content) <= max_chars:
        return content, False

    return content[:max_chars], True


class MarkItDownBackend:
    name = "markitdown"

    def extract(self, source: Path, request: ExtractRequest) -> tuple[str, dict]:
        from markitdown import MarkItDown

        converter = MarkItDown()
        result = converter.convert(str(source))
        raw_markdown = getattr(result, "markdown", None) or getattr(result, "text_content", "")
        markdown = "" if request.metadata_only else raw_markdown
        markdown, truncated = _apply_char_limit(markdown, request.max_chars)

        metadata = {
            "filename": source.name,
            "extension": source.suffix.lower(),
            "size_bytes": source.stat().st_size,
            "converter": self.name,
            "title": getattr(result, "title", None),
            "truncated": truncated,
            "raw_markdown_chars": len(raw_markdown),
        }

        return markdown, metadata
