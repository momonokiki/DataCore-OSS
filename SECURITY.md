# Security Policy

DataCore can store sensitive personal information, including receipts, financial statements, images, and extracted text. Treat every issue, log, screenshot, and sample file as potentially sensitive.

## Supported versions

There is currently no formal release/support matrix. Security fixes, when made, will generally target the current development branch.

## Reporting a vulnerability

Please do **not** publish credentials, exploit details, personal data, or a working attack against a live installation in a public issue.

Use GitHub's private vulnerability reporting / Security Advisory feature for this repository when it is enabled. If private reporting is not available, contact the repository owner through their GitHub profile without posting exploit details publicly.

This is an individually maintained hobby project. There is no guaranteed response or remediation SLA. Do not assume that a report has been received until the maintainer acknowledges it.

## Safe handling when testing

- Use synthetic receipts, statements, accounts, and identities.
- Never commit `.env`, API tokens, passwords, private keys, database dumps, CAS storage, uploaded files, or private logs.
- Rotate a credential immediately if it may have entered Git history; removing the current file is not sufficient.
- Do not expose the current Docker Compose deployment directly to the public internet. Review port bindings, default credentials, CORS, authentication, and host firewall rules first.
