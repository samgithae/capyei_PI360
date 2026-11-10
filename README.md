# CAP-YEI Placement Intelligence 360 (PI 360)

Application code. The plan, requirements, decisions and registers live in the
separate `planning/` package; task and requirement IDs (T-xxx, FR-xx) refer to it.

**Status:** Sprint 0 skeleton (T-019) with the ported Metronic shell (T-141).
No features yet: screens wait for the design sign-off (G2).

| Folder | What |
|---|---|
| `backend/` | Django 5.2 + Django REST Framework, PostgreSQL, Python 3.13 (uv) |
| `frontend/` | React 19 + TypeScript + Vite on the Metronic 9.5.0 kit |
| `docker-compose.yml` | Local stack: postgres, api, web |
| `.github/workflows/ci.yml` | Lint, tests, build, audit, image build |

## Rules

- **No real trainee data in this repository or in development**, ever (SEC-14).
  Use synthetic data. Spreadsheets are git-ignored for that reason.
- Session cookie auth with CSRF; no tokens in browser storage (ADR-023).
- Every permission is checked on the API; the UI only hides what the API forbids.

## Run locally

```bash
cp .env.example .env
docker compose up --build      # http://localhost:8080
```

Or without Docker (needs a local PostgreSQL, or set `DATABASE_URL`):

```bash
cd backend && uv sync && DJANGO_DEBUG=1 uv run python manage.py migrate && DJANGO_DEBUG=1 uv run python manage.py runserver
cd frontend && npm ci && npm run dev    # http://localhost:5173
```

## Checks

```bash
cd backend && uv run ruff check . && uv run pytest
cd frontend && npm run lint && npm run build
```

## Repository

Kept local until repository ownership is decided (D-032). Then it moves to the
CAP-YEI organisation with branch protection and required CI checks.
