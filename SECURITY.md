# Security Policy

## Reporting a vulnerability

Please do not disclose security issues publicly until they have been addressed.

Use the GitHub Security Advisories workflow for this repository, or contact the maintainer privately through the project’s official contact route before opening a public issue or PR.

## Sensitive information

This project may use environment variables such as `GEMINI_API_KEY` and local SQLite files. Do not commit:

- `.env` files
- API keys or tokens
- database files with local data
- private URLs or personal infrastructure details

If a secret is discovered in the repository, remove it from the working tree and rotate it before merging any public-facing change.
