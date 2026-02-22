# Repository Guidelines

## Project Structure & Module Organization
- Application code: `app/` (FastAPI routes in `main.py`, embeddings logic in `embeddings.py`, retrieval in `retrieval.py`, Celery tasks in `tasks.py`, auth providers in `auth_providers/`).
- Frontend assets: `app/templates/` (Jinja2 views) and `app/static/` (JS/CSS/assets).
- Infrastructure: `Dockerfile`, `docker-compose.yml`, environment config via `.env`, data volume at `./data` (Chroma store, uploads, admin hash).
- Dependencies: `requirements.txt`; entrypoint served by Gunicorn/Uvicorn.

## Build, Test, and Development Commands
- Run locally with Docker Compose (recommended):
  ```bash
  docker compose up --build
  ```
  Builds the app + worker images and starts Redis.
- Rebuild after code changes without wiping data:
  ```bash
  docker compose build app worker
  docker compose up -d app worker
  ```
- View logs:
  ```bash
  docker compose logs -f app
  docker compose logs -f worker
  ```

## Coding Style & Naming Conventions
- Python 3.11; follow PEP 8 with 4-space indents; prefer type hints for functions.
- Keep FastAPI routes thin; move logic to helpers (`embeddings.py`, `retrieval.py`, `utils.py`).
- Environment keys are UPPER_SNAKE_CASE; Jinja template IDs/classes should be kebab-case.
- Keep comments minimal and focused on non-obvious behavior.

## Testing Guidelines
- No formal test suite present; prefer adding fast unit tests with `pytest` if contributing.
- Name tests `test_<feature>.py`; keep them deterministic and side-effect free (avoid hitting OpenAI/Redis/Chroma—mock or fixture).
- If adding Celery logic, include a unit-level test for progress callbacks where possible.

## Commit & Pull Request Guidelines
- Use clear, descriptive commit messages in imperative mood (e.g., "Add redis progress polling").
- PRs should describe the change, deployment steps (if any), and testing performed; include screenshots for UI changes.
- Keep changes small and cohesive; update `README.md` or `AGENTS.md` when altering setup/developer workflow.

## Security & Configuration Tips
- Do not commit secrets; load from `.env`. Prefer `ADMIN_PASSWORD_HASH` over plain `ADMIN_PASSWORD`.
- The `./data` volume is persistent—wipe it intentionally with `docker compose down -v` only when you need a clean Chroma store.
