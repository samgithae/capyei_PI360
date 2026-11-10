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

## Import pipeline (T-040)

`apps/imports` (API under `/api/v1/imports/`). Flow: **template -> upload (dry run) -> approve -> commit -> rollback.**

- **Templates** map source column headers to target fields and are versioned: a change is a new version.
- **Upload** (`.csv` or `.xlsx`, up to the `import.max_upload_mb` setting) parses and validates only. It writes batch and row
  records and changes no participant. Re-uploading a file with the same hash is flagged (`duplicate_of`) and loads nothing new.
- **Rows** are `create`, `update` (same programme + enrollment number), `held` (with reasons) or `skip` (already loaded).
- **Commit** needs approval first. It runs in chunks of 500, one transaction each; a failed chunk rolls back alone and the batch
  is `partially_committed`; calling commit again resumes. Every change is written to `record_lineage` with before/after.
- **Rollback** (with a reason) undoes a batch unless a later batch changed the same records.
- `GET .../errors` downloads a CSV of held rows and warnings (row numbers and messages only, never the row's values).
- Permissions: `imports.run` (templates, upload, read, cancel) and `imports.commit` (approve, commit, rollback).
- Not yet: background jobs and progress (runs inside the request), file encryption at rest (the file itself is not stored,
  only its hash and rows), steward scope check per row, fuzzy duplicate matching (T-041), reconciliation report (T-042).

## Participant directory (T-058, T-043 core)

API (all record-scoped; out-of-scope ids return 404):
- `GET /api/v1/participants` - directory; filters `q` (name or enrollment no.), `programme`, `cohort`, `county`, `status`, `offset` (page size 50). With `cohort` set it is the cohort roster.
- `GET /api/v1/participants/<id>` - profile with enrollment history and residences; `contacts` only with `participants.view_contact`.
- `PATCH /api/v1/participants/<id>` - edit names, gender, status (`participants.edit`, audited).
- `GET /api/v1/participants/filters` - programme, cohort and county options.

UI: `/youth` (directory and roster via the cohort filter, filters kept in the URL) and `/youth/:id` (profile).

Deferred: extended profile (education, skills, experience; D-004, D-010), placement history tab (needs placements), residence and contact editing.

## Employer management (T-044)

API (`employers.view` reads, `employers.edit` changes):
- `GET/POST /api/v1/employers` - list (filters `q`, `status`, `sector`, `county`, `offset`) and create.
- `GET/PATCH /api/v1/employers/<id>`; `GET /api/v1/employers/<id>/history` (from the audit trail).
- `POST /api/v1/employers/<id>/contacts`, `PATCH/DELETE .../contacts/<cid>`; one primary contact per employer.
- `GET /api/v1/employers/check-name?name=` and `GET /api/v1/employers/filters`.

Duplicate-name warning: names are compared after normalising case, spacing and punctuation, plus a similarity score (0.88). A create or rename that matches returns 409 `duplicate_name` with the matches; resend with `confirm_duplicate: true` to proceed. Nothing is ever merged automatically (merge belongs to T-041/T-087).

UI: `/employers` (list, filters, add form with the warning) and `/employers/:id` (edit, contacts, history).

Not built: employer scope rules, contact-detail restriction, bulk employer import (T-087), opportunities (T-045).

## Opportunities (T-045)

Lives in `apps/employers` (CMP-05); same permissions as employers (`employers.view` / `employers.edit`).

API: `/api/v1/opportunities` (list with `q`, `status`, `kind`, `employer`, `offset`; create), `/<id>` (get, patch), `/<id>/transition` (`{"to": "open"|"closed"}`), `/<id>/history`, `/<id>/requirements` and `/<id>/requirements/<rid>`.

State machine: `draft -> open -> closed | expired`; `closed` and `expired` reopen to `open`. Opening needs a closing date today or later and an active employer. Closed and expired opportunities are locked (no edits to fields or requirements). Every transition is audited with the actor.

Expiry: `python manage.py expire_opportunities` marks open opportunities past their closing date as expired (system actor, idempotent). **No scheduler exists yet**, so it must be run daily by cron or the platform scheduler until one is built. Independently, `services.accepts_referrals(id)` is false for anything not open or past its closing date, so referrals (T-046) are blocked even before the job runs.

Requirements: typed by factor (skill, qualification, location, availability, other), each mandatory or preferred (FR-14).

Assumptions pending D-008/D-010: the draft state, "closing date required to open", and the field list. Not built: matching against requirements (T-060), employer-facing portal, owner officer.

## Duplicates, merge and reconciliation (T-041, T-042)

Lives in `apps/participants` (`duplicates.py`, `duplicate_views.py`) and `apps/imports`. Permissions: `duplicates.review` (see the queue, scan, dismiss, history) and `duplicates.merge` (merge, undo).

Detection (`participants.services.scan`): proposes pairs, never merges. Rules (proposals until D-004): same normalised name + same phone (0.95), nearly the same name (>= 0.88) + same phone (0.85), same name in the same programme with different enrollment numbers (0.80). Phones compare on their last 9 digits; a phone shared by more than 20 people is ignored. Scanning is repeatable and never reopens a dismissed pair. An import commit scans the records it created, so possible duplicates are queued for a steward right after a load (the lightweight quarantine; the full wizard is T-059).

Merge: the steward picks the surviving record and, per field, whose value to keep. Enrollments, contacts, source identifiers and residences move to the survivor; the other record stays in the database, hidden (`merged_into`), with a full snapshot so **Undo** restores it exactly. Blocked when both people are enrolled in the same course offering, and an import rollback is blocked while merges touch its records. A reason is required and every merge and undo is audited.

API: `GET /api/v1/participants/duplicates?status=open|dismissed`, `POST .../duplicates/scan`, `POST .../duplicates/<id>/dismiss`, `POST .../duplicates/<id>/merge` (`{survivor, fields: {field: "merged"}, reason}`), `GET /participants/merges`, `POST /participants/merges/<id>/undo`. Phones appear only with `participants.view_contact`.

Reconciliation (T-042): `GET /api/v1/imports/batches/<id>/reconciliation` (add `?download=csv` for a file). Every source row lands in exactly one bucket (created, updated, skipped, held, pending, rolled back), so `balanced` is true only when the buckets add up to the file's row count. It also compares per-cohort control totals with what PI 360 holds and lists held rows with their reasons, never their values. `GET /api/v1/imports/templates/<id>/contract` publishes the columns, required fields and load rules for the file's owner.

UI: **Duplicates** in the menu (`/duplicates`). Dev data: `scripts/seed_dev.py` includes one synthetic pair ("Grace Akinyi").

Not built: reconciliation screen in the UI (T-059 wizard), un-merging a record whose survivor was merged again (blocked by design), the R-15 "don't overwrite officer corrections" rule, employer duplicates (T-087).

## Import wizard and shared states (T-059, T-142 part)

Pages `/imports` (history), `/imports/new` (steps 1-2) and `/imports/:id` (steps 3-6; the step
comes from the batch's status, so leaving and coming back resumes where you were). Six of the
eight steps in doc 15 §3 are built: Upload, Map columns, Validate and review, Approve, Load,
Reconcile. **Not built:** cohort defaults (step 4) and field-by-field match review (step 6),
which need backend support and wait on D-059 (update vs add) and D-050 (mandatory fields).

- `POST /api/v1/imports/inspect` (`imports.run`): reads a file's headers, row count, empty
  columns, suggested mapping and any saved template that fits. Stores nothing.
- `src/components/states.tsx`: `LoadingState`, `EmptyState`, `ErrorState`, `Notice`, the shared
  data-region states from doc 20 §2. Other pages still use their own wording (to retrofit).
- `lib/api.ts` now sends `FormData` without forcing a JSON content type (needed for uploads).

## State retrofit (T-142)

The older pages (participants, employers, opportunities, admin users, overview, placeholder) now use `frontend/src/components/states.tsx`: `LoadingState`, `EmptyState`, `ErrorState` (with "Try again") and `Notice`. Detail pages show "not found" as an empty state on 404 and an error state otherwise.
