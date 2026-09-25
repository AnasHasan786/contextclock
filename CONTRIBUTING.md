# Contributing

Thank you for helping improve ContextClock.

## Local setup

### Backend

```bash
cd backend
python -m venv .venv
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
# macOS / Linux
# source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Then set the required values in the local `.env` file, especially `GEMINI_API_KEY`.

### Frontend

```bash
cd frontend
npm install
```

The frontend expects `NEXT_PUBLIC_API_URL` to point at the running backend, for example:

```bash
NEXT_PUBLIC_API_URL=http://localhost:8000
```

## Running the project

### Backend

```bash
cd backend
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend

```bash
cd frontend
npm run dev
```

## Validation

Run the backend tests from the virtual environment:

```bash
cd backend
.\.venv\Scripts\python -m pytest -q
```

Run the frontend production build:

```bash
cd frontend
npm run build
```

## Pull requests

Please keep changes focused and avoid unrelated refactoring. Include a short explanation of:

- what changed
- why it changed
- what was verified locally

## Repository hygiene

Do not commit:

- local `.env` values
- `.venv` folders
- generated `node_modules`, `.next`, or `.pytest_cache` files
- local SQLite databases

## Scope expectations

This repository is intentionally a research/prototype project. Changes should be clear, reproducible, and honest about limitations, especially around evaluation and external API usage.
