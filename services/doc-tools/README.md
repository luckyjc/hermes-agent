# doc-tools

Local document extraction sidecar used by Hermes.

Source now lives in the Hermes runtime repo:

`/home/lucky/.local/opt/hermes/services/doc-tools`

Runtime state remains outside the repo:

`/home/lucky/docker/doc-tools`

What it does:
- exposes a local-only HTTP API on `127.0.0.1:9478` by default
- wraps MarkItDown and Docling behind one stable extraction API
- uses a staged intake directory so host-native Hermes can hand files to the container safely
- keeps Docling on CPU-only PyTorch wheels during container builds
- keeps staged files, caches, temp files, and `.env` out of git

Current phase:
- real MarkItDown extraction for local staged files
- real Docling extraction and OCR for local staged files
- backend routing with fallback from MarkItDown to Docling for PDFs when needed
- health endpoint and structured extract support
- URLs still intentionally deferred to Hermes `web_extract`

Directory notes:
- repo source: `/home/lucky/.local/opt/hermes/services/doc-tools`
- state root: `${DOC_TOOLS_STATE_DIR:-/home/lucky/docker/doc-tools}`
- `intake/` contains staged input files Hermes wants extracted
- `cache/` is for backend/model/runtime cache
- `tmp/` is writable temp space for the container

Start from the repo source:
```bash
cd /home/lucky/.local/opt/hermes/services/doc-tools
mkdir -p /home/lucky/docker/doc-tools/{intake,cache,tmp}
docker compose build
docker compose up -d
```

Override state/env paths when needed:
```bash
DOC_TOOLS_STATE_DIR=/path/to/state \
DOC_TOOLS_ENV_FILE=/path/to/doc-tools.env \
  docker compose up -d
```

Check health:
```bash
curl -fsS http://127.0.0.1:9478/health
```

Example local extract request with MarkItDown:
```bash
cp /path/to/file.txt /home/lucky/docker/doc-tools/intake/sample.txt
curl -sS http://127.0.0.1:9478/extract \
  -H 'Content-Type: application/json' \
  -d '{
    "source": "/data/intake/sample.txt",
    "source_kind": "local_path",
    "backend": "markitdown",
    "mode": "markdown"
  }'
```

Example structured extract request with Docling:
```bash
curl -sS http://127.0.0.1:9478/extract \
  -H 'Content-Type: application/json' \
  -d '{
    "source": "/data/intake/sample.txt",
    "source_kind": "local_path",
    "backend": "docling",
    "mode": "structured"
  }'
```

Run tests inside the container:
```bash
cd /home/lucky/.local/opt/hermes/services/doc-tools
docker compose exec -T doc-tools pytest tests/test_health.py tests/test_routing.py tests/test_extract_api.py -q
```

Expected v1 policy:
- local files only through mounted intake path
- URLs stay with Hermes `web_extract`
- Hermes stages files into `/home/lucky/docker/doc-tools/intake/` before calling the service

Privacy-filter fit:
- doc-tools should extract raw Markdown/structured text
- redacted/shared extraction belongs in the Spark `document-ai` gateway path
- keep raw extraction and redacted output as separate fields; do not silently overwrite extracted text
- preferred integration is a Hermes-side routing policy, not public exposure of local doc-tools
