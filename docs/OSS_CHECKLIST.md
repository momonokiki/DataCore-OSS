# OSS publication checklist

This is a lightweight release checklist for an individually maintained project. It is not a demand for formal team processes.

## Applied in the preparation overlay

- [x] Add `.dockerignore`.
- [x] Expand `.gitignore` for environment files, local data, databases, backups, credentials, and caches.
- [x] Remove the hard-coded private-network Metabase URL by using `METABASE_URL`.
- [x] Remove the stale Dagster description from FastAPI metadata.
- [x] Correct the WebUI dependency-file typo by moving `httpx` into `app/webui/requirements.txt`.
- [x] Add lightweight contribution and security guidance.
- [x] Add basic GitHub Actions checks.
- [x] Correct README pipeline description against the submitted `ingest.py` route.

## Required before making the repository public

- [ ] Choose and add a root `LICENSE` (see `LICENSE_DECISION.md`).
- [ ] Run Gitleaks or an equivalent scanner against the full working tree and entire Git history.
- [ ] Inspect all binary files and local directories; verify no real receipts, statements, photos, user data, database dumps, or private logs are present.
- [ ] Confirm `git ls-files` does not include `.env`, `data/`, `storage/`, experiment output, or local caches. `.gitignore` does not untrack existing files.
- [ ] Review third-party licenses. In particular, YomiToku and its model weights are CC BY-NC-SA 4.0; see `LICENSE_DECISION.md`.
- [ ] Review CORS, authentication, default credentials, and the WebUI's published port. Do not expose the present setup directly to the public internet.
- [ ] Pin `metabase/metabase` to a tested version instead of `latest`.
- [ ] Review the unpinned Python dependencies and the simultaneous `opencv-python` / `opencv-python-headless` requirements.
- [ ] Run `./init.sh setup` from a clean clone and validate the real startup, database initialization, upload, OCR, and CSV parser paths.
- [ ] Verify documentation and implementation remain aligned after the next code changes.

## Optional after initial publication

- [ ] Add focused tests for L1 ingestion, L2 artifact provenance, L3 parser idempotency, and permissions.
- [ ] Add example fixtures containing synthetic data only.
- [ ] Add screenshots with all personal information removed.
- [ ] Add release notes and a Git tag when a reproducible setup has been verified.
