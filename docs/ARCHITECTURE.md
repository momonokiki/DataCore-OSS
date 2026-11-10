# DataCore architecture

This document describes the implementation visible in the submitted repository snapshot. Code and configuration remain the source of truth when implementation changes.

## 1. Runtime services

| Service | Responsibility | Host exposure in current Compose |
|---|---|---|
| `db` | PostgreSQL 16 + pgvector | Loopback by default (`DB_BIND`) |
| `redis` | Celery broker | No host port published |
| `fastapi` | HTTP API and ingestion | Loopback by default (`API_BIND`) |
| `celery-worker` | Background task execution | No host port published |
| `flower` | Celery monitoring UI | Loopback by default (`FLOWER_BIND`) |
| `webui` | Reflex interface | `WEBUI_PORT` published without an IP bind (host interfaces) |
| `metabase` | Optional analytics UI | `analytics` profile; loopback by default |

The UI's published port can be reachable from other devices on the host's network, depending on host firewall and network configuration. Do not assume that the full stack is loopback-only.

## 2. Logical data flow

```text
Client / Reflex UI
       |
       v
    FastAPI ---------> L1 ingestion service ---------> CAS file storage
       |                         |
       |                         +--------------------> PostgreSQL metadata
       |
       +---- Celery task chain ----> Redis broker ----> Celery worker
                                                    |       |
                                                    |       +--> L2 extracted artifacts
                                                    |       +--> L3 structured add-ons
                                                    v
                                                PostgreSQL
```

This is a logical diagram. Workers and API services may connect directly to PostgreSQL and CAS storage.

## 3. L1 — Raw

Main implementation:

- `app/layers/l1_raw/`
- `app/infrastructure/storage/`

Responsibilities:

- Receive file bytes and compute SHA-256 `file_hash`.
- Store content in local content-addressable storage.
- Record MIME type, file size, storage path, upload filename, and owner metadata.

`file_hash` identifies file content, not the business identity of a receipt, account transaction, or event.

## 4. L2 — Extracted

Main implementation: `app/layers/l2_extracted/`.

Current extraction families include media/EXIF information, OCR, image embeddings, and text embeddings. Individual implementations are separated from service interfaces and registries where applicable.

L2 artifacts are derived from L1. They should not replace original files.

## 5. L3 — Structured

Main implementation: `app/layers/l3_structured/addons/`.

Current domains visible in the repository include receipt parsing, financial CSV parsing, YomiToku layout reconstruction, and experimental receipt numeric classification. Add-ons own domain schemas and tables; the actual setup/dispatch process must be checked for each add-on.

## 6. Current general-file ingestion chain

`POST /api/v1/ingest` in `app/api/routes/ingest.py` saves each file in L1. When `trigger_pipeline=true`, the route launches this fixed Celery chain:

1. `tasks.extract_media_info`
2. `tasks.embed_image_file`
3. `tasks.ocr_file`
4. `tasks.embedding_file`
5. `tasks.reconstruct_yomitoku_layout`
6. `tasks.classify_receipt_numeric`

The route imports and defines `parse_file_task` elsewhere, but its chain invocation is commented out in the submitted snapshot. `tasks.parse_file` exists in `app/tasks.py` and checks for the `receipt` add-on, but it is not part of this route's active chain at this snapshot.

The layout and numeric-classification tasks have their own add-on enablement checks. They should be treated as experimental/optional behavior, not a universal receipt-processing guarantee.

Celery `chain` passes each task's return value as the next task's first argument. A task exception normally interrupts subsequent stages. A task that returns a failure-looking status dictionary without raising may still allow the chain to continue; these two cases must be distinguished in error handling.

## 7. Financial CSV path

`POST /api/v1/finance` in `app/api/routes/finance.py`:

1. Authenticates the user.
2. Saves the uploaded file bytes through the L1 ingestion service.
3. Dispatches `tasks.parse_finance_csv` for each stored `file_hash`.
4. Parses the bytes through the financial parser registry and writes domain records.

This path intentionally avoids image OCR and image embedding. The parser directory includes JCB and Japan Post Bank implementations.

## 8. Database initialization and migrations

- Alembic migrations live under `alembic/`.
- The DB initializer registers and initializes core models and seeds tools.
- L3 add-ons may provide their own setup scripts and tables.

Fresh-database initialization must be exercised from a clean clone before release. The presence of a model file does not by itself prove the model is loaded by every initializer path.

## 9. Operational limitations to review

- Redis has `depends_on: condition: service_started`, but no healthcheck; this only establishes container start ordering, not full broker readiness.
- `app/main.py` currently uses wildcard CORS origins together with credentials. Restrict origins before exposing the API beyond a trusted local environment.
- The WebUI port is published to host interfaces by the current Compose mapping.
- Metabase currently uses the mutable `latest` image tag; pin a tested version for reproducible builds.
- Retry, idempotency, and safe reprocessing guarantees need focused tests per task/add-on.
