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

## Staff authentication (CMP-03, T-034)

Local accounts, session cookie, CSRF token (ADR-023). Endpoints under `/api/v1/auth/`: `login`,
`logout`, `mfa/setup|confirm|verify`, `password/change`, `password/reset[/confirm]`.
Unauthenticated requests get 401; a signed-in user without permission gets 403.

- Lockout: `AUTH_MAX_FAILURES` (5) failures lock a username for `AUTH_LOCKOUT_SECONDS` (900).
- Sessions: idle `SESSION_IDLE_SECONDS` (1800), absolute `SESSION_ABSOLUTE_SECONDS` (28800).
- MFA (TOTP) is required for superusers, Django staff and the roles named in `AUTH_MFA_ROLES`
  (default `Administrator`). `AUTH_MFA_ALL_STAFF=1` extends it to everyone (open decision D-031).
- Reset emails use `EMAIL_BACKEND` (console until D-016/D-042) and link to `FRONTEND_URL`.
- `/admin/` is mounted only when `DJANGO_ENABLE_ADMIN` is on (default: debug). It bypasses lockout
  and MFA, so keep it off in staging and production.

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

## Access control (T-035)

- Roles are data (editable by an Administrator); the permission catalogue is in code (`apps/identity/catalogue.py`).
- Restricted permissions (`restricted.*`, `exports.identifiable`) are never in a role; they are granted per user with a purpose and an expiry.
- Record scope (all / assigned programme, cohort, region, officer) is applied through `apps.api.access`; out-of-scope records return 404.
- API views are deny-by-default: declare `required_permission`. `tests/test_authz_matrix.py` fails if a route is not classified.

## Reference data, flags and protected settings (T-038, T-057, T-039)

- **Reference data** lives in `apps.configuration` (sectors, the 47 seeded counties, sub-counties,
  wards, institutions, programmes, courses, cohorts, cohort-courses). Records are deactivated,
  never deleted; a code never changes; a rename keeps history in `ReferenceLabel`; source
  spellings resolve through approved `ReferenceAlias` rows. API: `/api/v1/config/reference/<kind>`.
- **Feature flags** are off unless a row exists and the environment (`APP_ENV`) and role audience
  match. Gate a view with `permission_classes = [HasPermission, FlagGate]` and `required_flag`;
  an off flag makes the route 404.
- **Protected settings** (`config.manage_protected`) need the caller's password, plus a TOTP code
  when they have an authenticator, and a reason. Failures are audited as `auth.step_up_failed`.
- **Participants** (`apps.participants`): officer-visible tables only. Scope is applied through
  `Participant.objects.visible_to(user)`. Restricted identity/background tables wait on D-063.

## Frontend auth and permission navigation (T-143)

- `frontend/src/lib/api.ts`: one fetch wrapper. Sends the session cookie, adds `X-CSRFToken` on unsafe methods,
  parses the `{"errors": [...]}` shape into `ApiError`, and fires `pi360:unauthenticated` on a 401.
- `frontend/src/auth/`: `AuthProvider` (state from `GET /api/v1/me`: roles, permissions, scope), `useAuth().can(permission)`,
  and the `RequireAuth` / `RequirePermission` route guards. The server remains the authority; the UI only hides what you cannot use.
- Login (`/login`): password, then MFA verify, or first-time enrolment (shows the `otpauth://` key, confirms with a code).
- Sidebar: each menu item carries a `permission`; `filterMenu` hides items and orphaned headings.
- Staff accounts: `/administration/users` (not `/admin`, which the dev proxy sends to Django's admin).
- Dev: the Vite server proxies `/api` and `^/admin/` to Django; with `DJANGO_DEBUG=1` Django trusts the `:5173` origin for CSRF.
