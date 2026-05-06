from pathlib import Path

from heuristics import choose_backend
from models import ExtractRequest


def test_choose_backend_prefers_docling_for_structured_mode() -> None:
    request = ExtractRequest(source="/data/intake/example.pdf", mode="structured")

    backend, fallback_chain = choose_backend(request)

    assert backend == "docling"
    assert fallback_chain == ["docling"]


def test_choose_backend_tries_markitdown_first_for_pdf() -> None:
    request = ExtractRequest(source=str(Path("/data/intake/example.pdf")))

    backend, fallback_chain = choose_backend(request)

    assert backend == "markitdown"
    assert fallback_chain == ["markitdown", "docling"]
