from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

import api
from config import get_settings
from main import app

client = TestClient(app)


def test_extract_uses_fallback_backend_when_primary_fails(monkeypatch, tmp_path) -> None:
    intake_root = tmp_path / "intake"
    intake_root.mkdir()
    sample_file = intake_root / "example.pdf"
    sample_file.write_text("fallback me", encoding="utf-8")

    settings = get_settings()
    monkeypatch.setattr(settings, "doc_tools_allowed_roots", str(intake_root))

    class FailingBackend:
        def extract(self, source: Path, request):
            raise RuntimeError("markitdown boom")

    class WorkingBackend:
        def extract(self, source: Path, request):
            return "docling output", {"converter": "docling", "structured_data": {"ok": True}}

    monkeypatch.setitem(api.BACKENDS, "markitdown", FailingBackend())
    monkeypatch.setitem(api.BACKENDS, "docling", WorkingBackend())

    response = client.post(
        "/extract",
        json={
            "source": str(sample_file),
            "source_kind": "local_path",
            "backend": "auto",
            "mode": "markdown",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["backend_used"] == "docling"
    assert payload["markdown"] == "docling output"
    assert payload["structured_data"] == {"ok": True}
    assert "Primary backend markitdown failed; used fallback docling" in payload["warnings"]


def test_extract_returns_structured_docling_payload(monkeypatch, tmp_path) -> None:
    intake_root = tmp_path / "intake"
    intake_root.mkdir()
    sample_file = intake_root / "example.pdf"
    sample_file.write_text("structured me", encoding="utf-8")

    settings = get_settings()
    monkeypatch.setattr(settings, "doc_tools_allowed_roots", str(intake_root))

    class StructuredDoclingBackend:
        def extract(self, source: Path, request):
            return "", {"converter": "docling", "structured_data": {"doc": {"pages": 1}}}

    monkeypatch.setitem(api.BACKENDS, "docling", StructuredDoclingBackend())

    response = client.post(
        "/extract",
        json={
            "source": str(sample_file),
            "source_kind": "local_path",
            "backend": "docling",
            "mode": "structured",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["backend_used"] == "docling"
    assert payload["structured_data"] == {"doc": {"pages": 1}}
    assert payload["metadata"]["converter"] == "docling"
