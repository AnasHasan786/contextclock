# Repository Readiness Report

## Project Overview

ContextClock is a memory-staleness monitoring prototype for AI agents. The backend computes a weighted score combining time decay, access anomaly, and Gemini-based contradiction detection for memory entries stored under a user + agent scope. The frontend exposes a local dashboard to create memories, inspect scores, and record actual usage.

## Current Repository Status

The repository currently contains:

- a FastAPI backend in [backend](../backend)
- a Next.js dashboard in [frontend](../frontend)
- a small evaluation library under [backend/app/evaluation](../backend/app/evaluation)
- an existing test suite under [backend/tests](../backend/tests)
- a minimal `.gitignore`, but it misses some local artifacts and secret files that should be protected

## Completed

- confirmed the backend app structure and runtime flow
- confirmed the frontend build status and backend test status in the local repo environment
- improved repository ignore rules for Python, Node, local secrets, and generated files
- added a safe environment template for required variables
- added project-level documentation for setup, architecture, and repo readiness
- documented security and contributing guidance for a public GitHub repo

## Remaining Issues

- no project license has been selected yet
- no production deployment configuration is present
- authentication and authorization are not implemented for the API
- the repository still contains local benchmark artifacts and machine-specific runtime files that should be reviewed before publishing

## Security Findings

- the backend currently expects a Gemini API key via the `GEMINI_API_KEY` environment variable
- a local `.env` file exists in the backend and contains a real API key; it must remain untracked and must be rotated if it was ever committed to a public remote
- the repository should not expose local SQLite database files or generated outputs in a public repo
- secret values and API keys are intentionally omitted from all documentation in this report

## Files That Should Be Committed

- [README.md](../README.md)
- [docs/architecture.md](architecture.md)
- [docs/repository-readiness.md](repository-readiness.md)
- [CONTRIBUTING.md](../CONTRIBUTING.md)
- [SECURITY.md](../SECURITY.md)
- [.gitignore](../.gitignore)
- [.env.example](../.env.example)
- [backend/requirements.txt](../backend/requirements.txt)
- [backend/.env.example](../backend/.env.example)
- [backend/app](../backend/app)
- [backend/tests](../backend/tests)
- [frontend/package.json](../frontend/package.json)
- [frontend/package-lock.json](../frontend/package-lock.json)
- [frontend/src](../frontend/src)
- [backend/app/evaluation/data/stale_eval.jsonl](../backend/app/evaluation/data/stale_eval.jsonl)

## Files That Should NOT Be Committed

- `.env` files in any folder
- local SQLite files such as `contextclock.db`
- virtual environments such as `.venv/`
- front-end build output such as `.next/`
- `node_modules/`
- `.pytest_cache/`
- local benchmark outputs such as smoke and stale evaluation JSON files that are diagnostic-only
- machine-specific local state and temporary files

## Documentation Status

- README is now project-specific and includes setup, run instructions, API endpoints, testing, and evaluation notes.
- architecture documentation exists and explains the main scoring pipeline.
- security guidance exists for responsible disclosure.
- contributing guidance exists for local development and validation.
- the project is documented honestly as a research-oriented local prototype; deployment instructions are not presented as production-ready.

## Reproducibility Status

Local reproducibility is documented and largely supported by the repository:

1. create backend venv
2. install Python requirements
3. create local env file from `.env.example`
4. run the FastAPI backend
5. install frontend dependencies and run the Next.js dashboard
6. run the backend test suite in the same environment

This is reproducible by another developer, provided they have a valid Gemini API key and a working Python + Node toolchain.

## Testing Status

The backend test suite was verified in the repository's Python virtual environment:

- 107 tests passed in 13.64s

The frontend build was also verified:

- Next.js production build completed successfully

This is an honest status based on the commands actually run in the current workspace.

## CI/CD Status

No GitHub Actions workflow existed before this audit. A minimal workflow is recommended for future public use, but the repository is currently local-only and has not been configured for a hosted deployment or automated release pipeline.

## Known Limitations

- no authenticated API layer
- no external database or cloud deployment configuration
- no license file yet
- evaluation scripts depend on live Gemini API usage and quota availability
- the system stores state locally in SQLite by default

## Manual Actions Required

- choose and add a license if the project is to be published under a specific legal open-source term
- rotate or remove any real secret currently stored in a local `.env` file before the repo is made public
- review whether the remaining evaluation output JSON files should remain in the repo or be moved to a separate research archive
- decide whether to keep the app as a local prototype or add deployment, auth, and persistence layers before a broader release
