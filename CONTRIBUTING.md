# Contributing to DataCore

Thanks for taking an interest in DataCore. This is an individually maintained project, developed at a hobby pace. Contributions are welcome, but there is no response-time or merge guarantee.

## Ways to contribute

- Report a reproducible bug or suggest a focused improvement through GitHub Issues.
- Improve documentation or examples.
- Submit a small pull request for a clearly scoped change.
- Develop an independent L2 plugin or L3 add-on and describe its input/output contract.

For a large change, open an issue first so the intended direction can be discussed before substantial work is done. There are no required meetings or project-management ceremonies.

## Before opening a pull request

1. Explain the problem and the behavior being changed.
2. Keep the change focused; avoid unrelated refactors.
3. Update documentation when behavior, configuration, or setup changes.
4. Do not include personal files, real financial data, credentials, tokens, database dumps, or private logs.
5. Include test steps and their results. If a test cannot be run locally, state that clearly.

## Basic checks

From the repository root:

```bash
bash -n init.sh
python -m compileall -q app
test -f .env || cp env.example .env
docker compose config --quiet
```

These are basic syntax/configuration checks, not a substitute for exercising the application against a clean database and representative test files. Use synthetic test data only.

## Architecture conventions

- Keep the original file in L1; derived artifacts belong in L2; domain-specific records belong in L3.
- Do not treat a file hash as a business-record identifier. Keep file identity and domain identity separate.
- Preserve provenance where practical: source file hash, artifact/tool identifiers, parser/model version, and relevant configuration.
- Prefer deterministic parsing for fixed-format inputs; use OCR/LLMs where they add value.
- Make add-on activation and setup behavior explicit. Do not silently introduce migrations or destructive data changes.
- Keep provider-specific assumptions configurable and document platform constraints.

## Review expectations

The maintainer makes the final decision on scope and merge. A pull request may be declined, deferred, or requested to be simplified. This is a hobby project, not a staffed support service.
