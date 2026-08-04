# SELFHOSTING

Operational defaults:
- source path: `/home/lucky/.local/opt/hermes/services/doc-tools`
- runtime state path: `${DOC_TOOLS_STATE_DIR:-/home/lucky/docker/doc-tools}`
- optional env file: `${DOC_TOOLS_ENV_FILE:-/home/lucky/docker/doc-tools/.env}`
- bind address: `127.0.0.1`
- default port: `9478`
- container name: `doc-tools`
- image tag: `doc-tools:local`
- Docling install path uses CPU-only PyTorch wheels via `--extra-index-url https://download.pytorch.org/whl/cpu`

Files and mounts:
- `${DOC_TOOLS_STATE_DIR}/intake` -> `/data/intake`
- `${DOC_TOOLS_STATE_DIR}/cache` -> `/data/cache`
- `${DOC_TOOLS_STATE_DIR}/tmp` -> `/tmp`

Manual workflow:
1. place or copy a test file into `/home/lucky/docker/doc-tools/intake/`
2. call `/extract` using the container-visible path under `/data/intake/`
3. inspect response and logs

Health and logs:
```bash
cd /home/lucky/.local/opt/hermes/services/doc-tools
docker compose ps
docker compose logs -f doc-tools
curl -fsS http://127.0.0.1:9478/health
```

Smoke checks:
```bash
cd /home/lucky/.local/opt/hermes/services/doc-tools
docker compose exec -T doc-tools pytest tests/test_health.py tests/test_routing.py tests/test_extract_api.py -q
cp fixtures/sample.txt /home/lucky/docker/doc-tools/intake/sample.txt
curl -sS http://127.0.0.1:9478/extract \
  -H 'Content-Type: application/json' \
  -d '{"source":"/data/intake/sample.txt","source_kind":"local_path","backend":"markitdown","mode":"markdown"}'
curl -sS http://127.0.0.1:9478/extract \
  -H 'Content-Type: application/json' \
  -d '{"source":"/data/intake/sample.txt","source_kind":"local_path","backend":"docling","mode":"structured"}'
```

OCR dependency guard:
```bash
docker compose exec -T doc-tools python - <<'PY'
import cv2, rapidocr, onnxruntime
print(cv2.__version__)
PY
```

Current limitations:
- `/extract` accepts only staged local files inside approved roots
- URL handling is intentionally deferred to Hermes `web_extract` for v1
- Docling is materially heavier than MarkItDown, so image builds are slower and larger even with CPU-only wheels

Next implementation phase:
- add Hermes-side routing between local doc-tools and Spark document-ai
- add richer MIME detection and backend-specific warnings
- add a broader fixture corpus with real PDFs, DOCX, XLSX, and scanned samples
- add explicit optional privacy-filter post-processing after extraction; keep raw and redacted outputs separate
