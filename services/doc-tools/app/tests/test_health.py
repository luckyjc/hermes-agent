from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["service"] == "doc-tools"
    assert payload["backends"]["markitdown"] is True
    assert payload["backends"]["docling"] is True


def test_docling_default_ocr_imports() -> None:
    # Docling's auto OCR path imports RapidOCR, which imports cv2. The slim
    # image needs OpenCV runtime libraries (libgl1/libglib2.0-0/libxcb1) for
    # cv2 to load; otherwise OCR silently degrades with "No OCR engine found"
    # and scanned/PDF OCR fails at runtime.
    import onnxruntime  # noqa: F401
    import rapidocr  # noqa: F401
