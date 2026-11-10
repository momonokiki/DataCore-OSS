# OSS publication preparation report

**Source inspected:** `repository(20261108-210830).txt` uploaded in this conversation (snapshot dated 2026-11-08 by filename). This report reflects that text snapshot only; it does not inspect the actual Git object database, untracked files, binary media, or files omitted from the export.

## Summary

The project has a coherent L1/L2/L3 direction and enough documentation to explain its purpose. It is suitable for an early-development repository once the publication blockers below are resolved. It is **not yet ready for an unconditional public release**: licensing, local-network residue, configuration hygiene, route/documentation mismatches, and a few security/reproducibility checks remain.

## Applied by this preparation package

- Tightened `.gitignore` for `.env.*`, personal `data/`, backups, databases, credentials, local caches, and generated WebUI state.
- Added `.dockerignore` so local secrets, personal data, experiments, caches, and VCS files are not copied into Docker build contexts.
- Replaced README content with a snapshot-accurate project description and removed links to documentation paths absent from the submitted file list.
- Added lightweight `CONTRIBUTING.md` and `SECURITY.md` that do not create meeting or project-management obligations.
- Added a GitHub Actions workflow for shell syntax, Python syntax, and Docker Compose configuration checks.
- Removed a hard-coded private overlay-network Metabase URL from the WebUI menu by making the URL configurable as `METABASE_URL`.
- Removed the same stale IP from the Reflex configuration comment.
- Corrected the stale Dagster description in the FastAPI app metadata.
- Added `httpx` to the correctly spelled WebUI requirements file and arranged to remove the misspelled `requirments.txt` file.
- Updated the environment template's application name and added a browser-facing Metabase URL setting.

## Findings from the submitted snapshot

### Privacy / secret scan

The plain-text export contained no matches for email addresses, common GitHub token formats, OpenAI API key formats, AWS access-key IDs, or PEM private-key headers. This is **not** a clean-bill-of-health statement for the real repository: binary files, ignored files, untracked files, `.git` history, and anything absent from the export were not checked.

The export contained a hard-coded private overlay-network IP address in the WebUI's commented Reflex config and Metabase link. It has been removed from the prepared overlay. `172.17.0.1` also appears as the Ollama host default in `app/core/config.py` and `env.example`; this is commonly used as a Docker bridge gateway, not a credential, but it is environment-specific and should remain configurable/documented.

### Documentation / implementation mismatches

- The submitted README and `docs/ARCHITECTURE.md` describe `tasks.parse_file` as the last stage of `/api/v1/ingest`.
- In the submitted `app/api/routes/ingest.py`, `parse_file_task.s()` is commented out. The active chain ends with `reconstruct_yomitoku_layout_task.s()` and `classify_receipt_numeric_task.s()`.
- `tasks.parse_file` still exists in `app/tasks.py`, but the submitted `/ingest` route does not call it.
- `app/main.py` describes the service as a pipeline “with Dagster”, although the implementation uses Celery.
- README links to `docs/development/INPUT_CONTRACT.md`, `PIPELINE.md`, `L2_PLUGINS.md`, and `L3_ADDONS.md`, but those paths were not present in the submitted file list.

### Repository hygiene

- No root `LICENSE`, `CONTRIBUTING.md`, `SECURITY.md`, `.dockerignore`, or `.github/workflows/` files appeared in the submitted file list.
- `.gitignore` ignored `.env`, `storage`, and `experiments`, but did not explicitly ignore root `data/`, `.env.*`, local database files, or backups.
- Both `app/webui/requirements.txt` and misspelled `app/webui/requirments.txt` appeared. The misspelled file adds `httpx`, while the correctly spelled file contains only Reflex; the WebUI state imports `httpx`.
- `docker-compose.yml` uses `metabase/metabase:latest`, which makes the image version non-reproducible.
- The root dependency file has unpinned entries (`redis>=5.0.0`, `Pyjwt`, `transformers`) and both `opencv-python` and `opencv-python-headless` are present at different versions. Review this before publishing a reproducible setup.
- `scripts/test_db_step1.py` through `test_db_step5.py` are manual database scripts, not a conventional automated test suite. Some appear tied to older schema names; check before presenting them as current tests.

### Security / deployment posture

- `app/main.py` configures CORS with `allow_origins=["*"]` and `allow_credentials=True`. Review and restrict this before use outside a trusted local environment.
- The WebUI port is published without a loopback-only bind in the submitted Compose file. Other exposed ports default to loopback, and Redis has no host port publication.
- The sample DB and Flower passwords are placeholders. The setup script generates a JWT secret, but users should change service credentials before allowing access beyond the local machine.
- `metabase/metabase:latest` should be pinned to a tested version before a tagged release.

## Must resolve before public publication

1. Choose and add a root `LICENSE`. See [License decision](LICENSE_DECISION.md). Until then, do not present the repository as having a selected OSS license.
2. Apply this overlay to the actual working tree, then inspect `git status`, `git ls-files`, and the final diff.
3. Run a secret scanner against the full repository and **all Git history** (for example, Gitleaks). If a credential ever entered history, rotate it; removing the current file is insufficient.
4. Inspect the actual `data/`, `storage/`, `experiments/`, uploads, database dumps, screenshots, and binary assets. The text export cannot verify them.
5. Decide how to handle YomiToku's CC BY-NC-SA 4.0 component and document its third-party license separately.
6. Restrict CORS and review authentication, default passwords, and WebUI port binding before recommending LAN or internet exposure.
7. Pin the Metabase image and decide whether to pin currently unpinned Python dependencies. Reconcile the two OpenCV distributions.
8. Perform a clean `./init.sh setup` on a fresh clone/machine. The provided CI workflow only performs syntax and Compose-configuration checks; it does not prove the full stack starts or processes real files correctly.

## Safe first public milestone

After the blockers are resolved, publish as an early-development release (for example, `0.1.0`) with explicit caveats. Do not call it production-ready and do not promise support response times.
