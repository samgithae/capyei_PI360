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
cd backend && uv run ruff check . && uv run lint-imports && uv run pytest
cd frontend && npm run lint && npm run build
```

After changing an API, regenerate the committed schema (CI fails if it is stale):

```bash
cd backend && DJANGO_DEBUG=1 uv run python manage.py spectacular --validate --file openapi.yaml
```

## Backend structure (doc 04 §4)

- `backend/apps/<module>/`: one Django app per component (CMP-03 to CMP-15).
  Another module may import only `apps.<module>.services`, never its models or
  views. `apps/api/` holds the shared API conventions (CMP-02).
- `backend/pi360_rules/`: the rules engine (CMP-08). Pure Python; no Django.
- Allowed dependencies are import-linter contracts in `backend/pyproject.toml`,
  copied from doc 04 §4.1. Changing one is an architecture change: update doc 04 first.
- API errors are `application/problem+json` (RFC 9457) with a `request_id`.
  Every response carries `X-Request-ID`; logs are JSON lines with the same ID
  (`LOG_FORMAT=text` for plain local logs).

## Audit trail (CMP-13)

Other modules write events with `apps.audit.services.record(...)`, in the same transaction as the
change. Events are append-only: PostgreSQL triggers reject UPDATE, DELETE and TRUNCATE, and each
row's hash covers the previous row's hash. Check the chain with:

```bash
cd backend && uv run python manage.py verify_audit_chain
```

In production run the app as a database role without UPDATE/DELETE on `audit_auditevent` and
migrate as a different role. `backend/apps/audit/COVERAGE.md` lists what must be audited.
Audit tests need PostgreSQL (CI has it); on SQLite they skip.

## Repository

Kept local until repository ownership is decided (D-032). Then it moves to the
CAP-YEI organisation with branch protection and required CI checks.
