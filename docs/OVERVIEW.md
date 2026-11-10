# DataCore system overview

DataCore is a personal data infrastructure project. It accepts original files, preserves them, extracts machine-readable information, and stores domain-specific structured data so that the data can be searched and reused outside a single application.

## Design principles

1. **Preserve originals.** L1 stores the original file and its identity. OCR text, embeddings, and parsed records are derived outputs.
2. **Separate content identity from record identity.** `file_hash` identifies file bytes; UUIDs and domain keys identify uploads, artifacts, transactions, and other records.
3. **Separate responsibilities.** L1 is raw storage, L2 is extracted/derived data, and L3 is domain-specific structure.
4. **Choose processing by input type.** Images/documents may need OCR and embeddings; a fixed-format CSV may be parsed deterministically.
5. **Keep AI replaceable.** Use deterministic code where possible and treat model outputs as derived data that can be regenerated or reviewed.
6. **Preserve provenance where practical.** Retain links between source files, extracted artifacts, tools, and structured records.

## Layers

- **L1 — Raw:** uploaded files, SHA-256 `file_hash`, CAS storage, and upload ownership metadata.
- **L2 — Extracted:** EXIF/media information, OCR artifacts, and image/text embeddings.
- **L3 — Structured:** domain models such as receipt totals/items and financial statements/transactions.

Not every input path must pass through all three layers. The current financial CSV route stores the original bytes in L1 and parses them directly into L3.

## Main components

- Reflex: Web UI
- FastAPI: authentication, file ingestion, financial CSV ingestion, receipt review, and search endpoints
- Celery + Redis: asynchronous task processing
- PostgreSQL + pgvector: metadata, artifacts, and structured records
- Local CAS storage: original files
- Flower: task monitoring
- Metabase: optional analytics UI

## Current input paths in the submitted snapshot

### General file ingestion

`POST /api/v1/ingest` saves files through `L1FileIngestionService` and, when `trigger_pipeline=true`, starts this Celery chain:

`extract_media_info` → `embed_image_file` → `ocr_file` → `embedding_file` → `reconstruct_yomitoku_layout` → `classify_receipt_numeric`.

The final stages are add-on/experimental processing steps. Although `tasks.parse_file` exists, its invocation is commented out in the current route. Therefore, the current route should not be described as automatically running the standard `receipt` parser.

### Financial CSV ingestion

`POST /api/v1/finance` stores the original CSV in L1 and dispatches `tasks.parse_finance_csv`. The parser registry includes JCB and Japan Post Bank parser implementations. It is a dedicated path and does not need to run image OCR first.

## Current limitations

- The project is under active development; APIs and schemas may change.
- Current task chains are explicit and fixed in route code; this is not yet a general workflow orchestrator.
- Retry, idempotency, and complete reprocessing guarantees must be verified per task and add-on.
- Local-first operation does not by itself make a deployment secure; network exposure, credentials, backups, and access controls require review.
