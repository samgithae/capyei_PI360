# PI 360: project guide and status

Living handover document for the next developer or AI. Read it first, then `README.md` (per-feature API
notes), `CLAUDE.md` one level up (how to start the app), and `frontend/UI-STANDARDS.md`. Update this file
when a phase closes, a rule changes or a decision lands.

Last updated: **2026-11-23**. `main` at `github.com/samgithae/capyei_PI360` is at `e1a40e2`; CI was green on
the last code commit (`9e3a85f`). The working tree is clean except one untracked, stale file
(`docs/pilot-guide.html`, safe to delete; `docs/walkthrough.html` replaced it).

Where the other material lives:

| What | Where |
|---|---|
| Plan, requirements, ADRs, data model, decisions, risks (task IDs `T-xxx`, decisions `D-xxx`, requirements `FR-xx`) | `../planning/` (outside git). Key files: `01_Implementation_Plan.md`, `02_WBS.md`, `04_Technical_Architecture_and_ADRs.md`, `12_Client_Clarification_and_Decision_Register.md`, `registers/decisions.csv` |
| Per-session history, every decision with its reason, what was verified | Obsidian note `Claude Handoff/capyei-pi360.md` (append-only; read the last entry first) |
| How to test the whole app by hand (32 steps, 9 parts) | `docs/walkthrough.md` and the interactive `docs/walkthrough.html` |
| Design notes | `docs/employer-portal-plan.md` (built; read its decisions table), `docs/learner-support-design.md` (not built), `docs/data-protection-review.md`, `docs/m2-review.md` |
| In-app help for end users | `frontend/src/pages/help/content-*.ts` (checked by `guides.test.ts`) |

---

## 1. What the system is

**CAP-YEI Placement Intelligence 360** helps a youth-employment programme (CAP-YEI, "Go Blue" cohorts) move
trained young people into work. It keeps one record per young person, their employers and opportunities, the
referral from youth to opportunity, the placement, and follow-up checks afterwards, and it turns that into
decision support for staff, employers and funders.

Three kinds of user, one app (Metronic 9 shell), one API:

| User | Sign-in | Lands on | Sees |
|---|---|---|---|
| **Staff** (Administrator, Data steward, Placement officer, Manager, M&E roles; roles are data) | username + password (+ TOTP for admins) | `/` project dashboard | Everything their role and **record scope** allows |
| **Youth** (learner portal) | invite link, then e-mail + password | `/me` | Own record, own referrals/opportunities, own placement, own CV. Never scores, rejection reasons or staff notes |
| **Employer contact** (employer portal) | invite link from staff, then e-mail + password | `/employer` | Only their own company: profile, opportunities, referrals, team. Never scores, staff notes or staff names. Candidate contact details only after "selected" |

Youth and employer accounts are **invite-only**; there is no self-registration.

The "intelligence" is three rule-driven modules, all driven by admin-editable rules and settings, never
hard-coded figures:

- **Module A, support priority** (`/support`): flags youth who need attention (unsuccessful or stalled referral,
  ready but never referred). "Mark reviewed" pauses a flag.
- **Module B, compatibility** (interim): "Suggested youth" on an opportunity shows "Preferred: X of Y" and ranks by
  it. No percentage score until the weights are approved (D-009).
- **Module C, employer evidence/reliability**: employer card with referral counts, a retention-after-placement
  rate from completed check-ins, and officer-logged feedback. Each indicator shows its count and is hidden
  ("Insufficient evidence") below an admin-set minimum. No overall rating.

---

## 2. Run, test, log in

```bash
# Persistent Postgres dev database (the only one to use for hand-testing)
open -a Docker && until docker info >/dev/null 2>&1; do sleep 2; done
cd pi360 && sh scripts/dev-db.sh up                        # 127.0.0.1:5433
cd backend && DJANGO_DEBUG=1 DATABASE_URL="$(sh ../scripts/dev-db.sh url)" uv run python manage.py migrate
```

Then start the launch entries `pi360-api-dev` (API on 8010) and `pi360-web-dev` (web on 5174) from
`.claude/launch.json`; the app is at http://localhost:5174. Never use the `pi360-api` / `pi360-web` entries
(throwaway SQLite in `/tmp`) for user testing. `dev-db.sh` also has `down`, `backup` and `restore`.
`dev-db.sh url` contains the password: never paste it anywhere.

Full stack in Docker: `docker compose up --build` (http://localhost:8080). Settings come from `.env`
(`.env.example` lists them).

**Checks (run before every commit; CI runs the same):**

```bash
cd backend  && uv run ruff check . && uv run ruff format --check . && uv run lint-imports \
            && uv run python manage.py makemigrations --check --dry-run \
            && uv run python manage.py spectacular --validate --fail-on-warn --file openapi.yaml \
            && uv run pytest
cd frontend && npx prettier --write src && npm run typecheck && npm run lint && npx vitest run && npm run build
cd frontend && npm run e2e         # Playwright + axe; own ports 8020/5190, throwaway SQLite, needs Chrome
```

If `openapi.yaml` changes, commit it (CI fails on a stale one). Audit tests need PostgreSQL (they skip on SQLite).

**Dev accounts.** `backend/scripts/seed_dev.py` creates `dev.admin` (Administrator), `dev.steward` (Data steward),
`dev.officer` (Placement officer), `dev.viewer` (Manager) and, at the synthetic company "Synthetic Traders Ltd",
`dev.boss@synthetic-traders.example` (Company admin) and `dev.viewer@synthetic-traders.example` (Employer
viewer). Passwords are in that file only, nowhere else. Do not reset or invent passwords for real users.

**Making a youth or employer test login.** Both are invite-only. Invite through the real services
(`apps.portal.services.send_invite` for a youth who has an e-mail on file, `apps.employer_portal.services.invite`
for a company contact), from `manage.py shell` with `DJANGO_DEBUG=1`; the invite link prints to the console
(`EMAIL_BACKEND` is console). Normal activation enforces the password validators (12+ characters, not common,
not numeric); a short test password needs a direct `set_password` plus `is_active=True` and is acceptable on the
dev database only. Remember to delete such accounts before any real data load.

---

## 3. Architecture

**Stack.** Backend: Django 5.2 + Django REST Framework, PostgreSQL 17, Python 3.13, `uv`. Frontend: React 19 +
TypeScript + Vite on the Metronic 9.5 kit (Tailwind, Radix, recharts). Auth: session cookie + CSRF, no tokens in
browser storage. CI: GitHub Actions jobs `backend`, `frontend`, `e2e`, `images`.

**Repo layout.**

```
backend/apps/<module>/      one Django app per component (CMP-xx); models, services, views, urls, migrations
backend/pi360_rules/        the rules engine: pure Python, no Django, ten operators, pass/fail/unknown results
backend/scripts/            seed_dev.py (synthetic dev data), go_blue_dry_run.py (throwaway DBs only)
backend/tests/              pytest; test_authz_matrix.py and test_architecture.py are guardrails
backend/openapi.yaml        generated API schema, committed
frontend/src/pages/<area>/  screens; shared pieces in components/shared and components/ui (Metronic)
frontend/src/auth, lib/api.ts, routing/app-routing-setup.tsx, config/layout-1.config.tsx (sidebar)
frontend/e2e/               Playwright tests and axe accessibility scans
docs/  scripts/  sample-data/  docker-compose*.yml
```

**Backend modules** (`backend/apps/`):

| Module | Owns |
|---|---|
| `api` | Shared API conventions: problem+json errors with `request_id`, record-scope helpers (`apps.api.access`), deny-by-default permission classes. Imports no domain module |
| `identity` | Staff accounts, roles (data) and the permission catalogue (`catalogue.py`, code), lockout, MFA (TOTP), sessions, per-user access **grants** for restricted permissions |
| `audit` | Append-only hash-chained audit events (`audit.services.record(...)` in the same transaction as the change); DB triggers reject UPDATE/DELETE. `verify_audit_chain` command |
| `configuration` | Reference data (sectors, 47 counties, 290 sub-counties, 1,448 wards, institutions, projects, courses, cohorts, qualification levels and grades), feature flags, protected settings |
| `participants` | Youth records: enrollments, residences, contacts, education, skills, work experience, consent, duplicates and merge, similar-name search, MIS corrections, CV; export field catalogue |
| `employers` | Employers, contacts, opportunities (+ requirements, skills, expiry job), duplicate-name warning, logo/description, archive |
| `referrals` | Referral workflow, stages, reason codes, corrections, reassign, interview details, "why suggested", officer-logged employer feedback |
| `casework` | Support interventions and case queues |
| `placements` | Placements and employment episodes, status mapping, duplicate-placement warning, **follow-up schedule and check-ins** |
| `intelligence` | Rule sets and versions (draft, in review, approved, active, retired), rule **settings registry** (`settings_registry.py`), Modules A/B/C |
| `imports` | Import pipeline: templates, dry run, approve, commit, rollback, reconciliation, sign-off, cohort defaults, field-diff review, placement import, employer clustering, promote extra data |
| `dataquality` | Nine data-quality rules (list the youth that fail), MIS corrections and their export |
| `reporting` | Dashboard and drill-down (`services.py`), the **five stakeholder reports** (`reports.py`, PDF/Excel in `report_files.py`), table exports (`exports.py`) |
| `retention` | Data-retention classes, periods, approvals and the `run_retention` job (first class: imported source rows) |
| `portal` | Youth learner portal: invites, activation, self-service (own record, CV, opportunities, placement, notifications) |
| `employer_portal` | `EmployerMember`, `EmployerInvite`, employer-scoped data APIs, dashboard, team and roles |
| `platform` | Health, request-id logging, observability |

**Hard rules enforced by tests.**

- A module may import another only through `apps.<module>.services`, never its models or views. The allowed
  graph is the import-linter contracts in `backend/pyproject.toml` (copied from planning doc 04 §4.1;
  `lint-imports` currently keeps 17). Changing a contract is an architecture change: update doc 04 first. When a
  module needs another's data, add a re-export in the owner's `services` (examples: `participants.report_options()`,
  `employers/own.py`, `referrals/own.py`).
- Every route must be classified in `tests/test_authz_matrix.py`; every view declares `required_permission`.
  Permissions are enforced on the API; the UI only hides what the API forbids.
- Serializer class names are unique across apps (spectacular fails otherwise).
- Record scope (all / project / cohort / region / officer) is applied with `Model.objects.visible_to(user)` and
  `apps.api.access`; an out-of-scope id returns 404, not 403.
- DRF reads `?format=` as a renderer override, so exports use `file_format`.
- "Programme" was renamed to "Project" everywhere on 23 Nov 2026 (D-070, NEW-069): model `Project`,
  fields `project`/`project_code`, scope kind `project`, reference kind `projects`. There is no API
  alias. Importers still accept "Programme" / "Programme code" headers (`tests/test_project_rename.py`).
  Audit events and export logs written before the rename keep the old word; they are history.

**Cross-cutting conventions.**

- Roles are database rows; the permission catalogue is code. Restricted permissions (`restricted.*`,
  `exports.identifiable`) can never be in a role: they are granted per person with a purpose and an end date
  (max 365 days) at Administration > Access grants. Employer roles are the roles whose every permission starts with
  `employer.`; a company admin can never hand out a staff role.
- Feature flags (`configuration`): off unless a row exists and environment/audience match; an off flag makes the
  route 404. Current flags: `consent_tracking` (off), `employer_self_publish` (off: an employer "open" is a
  publish request staff approve or decline), `employer_mfa_required` (off; can name roles). All editable and
  audited from the admin pages.
- **Rule settings** (`intelligence/settings_registry.py`, editable at Rules > Settings, audited, defaults in code):
  `employer.min_referrals` (5), `employer.min_feedback`, `employer.positive_rating`,
  `employer.min_retention_checks`, `rules.review_days` (working value), `support.*` (five, D-026, unapproved),
  `exports.small_cell` (5). Follow-up steps are data (`FollowUpStep`): 30 d, 90 d, 183 d, 365 d, 730 d; a change
  affects new placements only. `STALE_AFTER_DAYS` 30 and `DUE_SOON_DAYS` 7 in `placements/followups.py` are
  constants, not client decisions.
- **Delete means archive.** No hard deletes of business records; `archived_at`, restorable, gated by
  `records.archive`, audited `<type>.archived` / `.restored`. Lists hide archived rows unless "Show archived".
  An archived employer hides its opportunities and is ignored by duplicate checks and pickers.
- **Audit every write.** Audit entries for contacts and exports record kinds, filters, counts and field keys,
  never names or values.
- Errors are RFC 9457 `application/problem+json`; every response carries `X-Request-ID`; logs are JSON lines.
- Sessions: idle 1800 s, absolute 28800 s; lockout after 5 failures for 900 s. MFA required for Administrator
  (`AUTH_MFA_ROLES`); `AUTH_MFA_ALL_STAFF=1` widens it (D-031). `/admin/` (Django) is debug-only.
- Management commands: `expire_opportunities` (daily; compose `scheduler` runs it), `load_initial_rules`,
  `run_retention` (dry run by default), `purge_exports`, `verify_audit_chain`.

---

## 4. What is built (state at 2026-11-23)

Everything below is committed and pushed unless it says otherwise.

**Foundations.** Skeleton, CI, Metronic shell, staff auth with MFA, RBAC + record scope, audit chain, user admin,
reference data and admin pages for every list, feature flags, protected settings (step-up with password/TOTP).

**Data in.** Import wizard (template, inspect, upload as dry run, approve, commit in 500-row chunks, rollback,
reconciliation, sign-off, cohort defaults, field-difference review, any column kept as extra data), duplicates
queue and merge, Go Blue dry run script, placement import with employer clustering (D-064 and D-066 await
CAP-YEI). Officers can import what they own.

**Youth.** Directory and profile, every field editable (core, enrollments, residence, contacts, education with
qualification level/grade, skills picker, work experience), "Add youth" with duplicate warnings, search that
tolerates word order and near-spellings (thresholds in `participants/similar.py` are proposals), consent card
(behind `consent_tracking`), CV and PDF CV, archive/restore.

**Employers and opportunities.** CRUD with multi-county/multi-sector, logo, description, one People list,
duplicate-name warning, opportunity state machine (`draft` > `open` > `closed|expired`, expiry job), requirements
typed by factor with mandatory/preferred and a skills picker, minimum grade.

**Referral to placement.** Referral stages and reason codes (editable), "why suggested", candidate CV for the
employer, interview details, "Record placement" from a Selected/Placed referral (a referral never creates a
placement by itself), duplicate-placement warning (409 `possible_duplicate`, resend with `confirm_duplicate`),
placement episodes, verification, configurable follow-up schedule with check-ins, attempts and evidence.

**Cases and support priority.** `/cases` queues and interventions; `/support` Module A queue with Mark reviewed.

**Rules.** Engine plus versioned rule sets with a full lifecycle; the Administrator approves for now (D-009). Three
draft rule sets (`support-priority`, `compatibility-default`, `employer-reliability`) loaded by
`load_initial_rules`; every value awaits sponsor approval.

**Insight.**

- **Dashboard** `/`: KPI tiles, funnel, gender, pipeline, trend, age, county, needs-attention list, metric
  definitions; every number opens the list of records it counts (`/dashboard/list`, API `reporting/drilldown`) so a
  tile and its list cannot disagree. Placed = a Placement mapped as placed, or a referral at Placed.
- **Five reports** (`/reports`, `/reports/<slug>`): project-scorecard, placement-outcomes, equity-and-reach,
  retention, employer-pipeline. Filters kept in the URL, tiles, charts, tables, definitions, "Not captured yet"
  notes. API `GET reporting/reports/filters`, `GET reporting/reports/<slug>`,
  `POST reporting/reports/<slug>/export?file_format=pdf|xlsx` (nothing stored; each export audited with no names or
  figures). Open to anyone with `reports.view_aggregate`; numbers respect the viewer's record scope; exports show
  true numbers (the user's decision). Retention shows a rate only after `employer.min_retention_checks`; an
  unreachable youth is never counted as job loss. Disability is not collected (shown as a data gap).
- **Table exports** (`POST exports/table/<table>`; youth, employers, opportunities, referrals, placements,
  followups): CSV or Excel of exactly the filtered rows, with a field picker per table (catalogues in
  `reporting/exports.py` and `participants/export_fields.py`). Needs grant-only `exports.identifiable` plus a stated
  purpose; streamed, not stored; `ExportLog` and audit hold filters, count, purpose and field keys only. Youth
  exports can include phone, email, address and date of birth (flagged Sensitive, ticked by default). No national ID
  is stored. The older de-identified backend (`exports.deidentified`, `purge_exports`) is kept without UI until D-045.

**Data governance.** Data quality (`/data-quality`; nine rules, MIS corrections kept as was/now/who/when, an import
never overwrites an open correction; age bounds 14 to 35 are provisional), consent (minimum, flag off), data
retention (per-class period, basis and separate approval; no period is set, so nothing is cleared until D-015).

**Learner portal** (`/me`): dashboard, My opportunities (list and detail), My placement, My details/profile, CV,
skills, grades, notifications, mobile-optimised. **Phase 3 (support tickets and 1 wk/30/60/90 d/6 m learner
check-ins) is not built**; design in `docs/learner-support-design.md`.

**Employer portal** (`/employer`, built in six phases; see `docs/employer-portal-plan.md`, whose "proposal"
status line predates the build): company dashboard, opportunities with publish-request flow, referrals with safe
CV and plain "why suggested", company profile and contacts, People (team and roles), staff-side "Portal accounts"
and awaiting-approval screens, admin page `/administration/employer-portal` for the two flags. Companies may move a
referral only to under_review, interview, selected or rejected (rejection needs a reason); placed/closed/withdrawn
stay staff-only. One user belongs to one company; the last active Company admin cannot be demoted or suspended.

**Shared UI.** `/account` (change password) for every signed-in user, in-app Help centre, e2e and axe accessibility
scans (WCAG 2 A/AA) of the sign-in page, 16 signed-in screens and each youth tab.

**Test counts (last recorded 2026-11-19):** backend full suite green (about 38 report tests, 35 employer-data, 34
employer-portal and many more); frontend vitest 161 tests; lint-imports 17 contracts kept. Re-run to confirm.

---

## 5. Decisions

The register (`planning/registers/decisions.csv`, markdown copy in doc 12) is owned by CAP-YEI. We do not flip a
status ourselves: an answer relayed by the implementer is recorded as "Relayed ... working basis".

| State | Decisions |
|---|---|
| **Decided** | D-004 (Go Blue 2021/2022 cohorts only; the enrollment number is the key; National ID is not a safe key), D-009 (the Administrator approves rule versions for now; review cadence still to set), D-012 (follow-up 30 d, 90 d, 6/12/24 months), D-013 (show employer indicators with the count, hide below a minimum, starts at 5), D-028 (early follow-up 30 d, early retention 90 d), D-037 (keep current referral stages, reason codes editable), D-060 (Metronic 9) |
| **Proposed, not final** | D-015 (provisional data-protection basis; the data protection lead has not answered; **production import stays blocked**), D-026 (starting support thresholds, marked unapproved until the placement lead approves), D-045 (keep current export rules; DPO to confirm), D-025 (user's working basis: option (a), not marked in the register), D-023 |
| **Open and gating** | D-001 (YDM assessment scope; gates T-049, T-062, T-083 to T-085), D-008 (compatibility factors and weights), D-002/D-003 (YDM), D-005 (MIS integration), D-006/D-007 (scope, self-service), D-014 (record scope rules), D-016/D-042 (e-mail provider; today the console backend), D-018/D-030/D-034 (hosting, backup, fairness), D-031 (MFA for all staff), D-032 (repository ownership), D-059/D-050 (import update-vs-add, mandatory fields), D-063 (restricted identity tables) |

Working decisions made while building, all labelled in code and docs as pending CAP-YEI:
the draft opportunity state and "closing date needed to open", the duplicate scan thresholds, age bounds 14 to 35,
dashboard metric definitions marked "working", the 5/5/5 minimums, the 90-day review cadence.

---

## 6. What is left

Mapped to WBS task IDs (`planning/registers/wbs.csv`; its Status column was never maintained, so trust this section).

**Not started or blocked on a decision**

| Task | What | Blocker |
|---|---|---|
| T-049, T-062, T-083 to T-085, T-088 | YDM assessment capture, YDM in matching, calculation engine, results views, test packs | D-001 (optional) |
| T-056 | MIS API adapter | D-005 (only if confirmed) |
| T-061 | Dedicated match review screen (Module B interim form exists) | D-008, D-025 |
| T-068 | Rule simulation and validation in CI | none; do next |
| T-069/T-070 (partial) | Metric definitions approval; retention, training completion, skills demand, predictive and staff-productivity tiles are not built | CAP-YEI approval; training completion and skills demand data are not captured |
| T-072 | Youth self-service phase 3 (support tickets, learner check-ins) | design questions (who owns tickets, phone check-ins) |
| T-076, T-030 | Staging/production environment as code, monitoring, restore drill 1 | D-018, D-030; only `docker-compose` exists |
| T-077 | Security hardening and internal review. **Remove the DEBUG-only MFA bypass before go-live** | none |
| T-079, T-080, T-081 | Technical documentation set, user guides (help guides exist), G3 gate | none |
| M4 to M7 (T-090 to T-136) | System/integration/security/performance/accessibility testing, UAT, production load, hypercare, handover | gated by the above |

**Open items and known gaps**

- Production import is blocked on D-015. No retention period is set or approved.
- The real Go Blue data (2,699 enrollment rows, 2,572 placement rows) is imported only on the real system. The dev
  DB holds about 64 synthetic youth, so report and dashboard numbers there are small. The MIS extract has not been
  seen, and about 23 repeated National IDs are not investigated as a data-quality item.
- Reports: the Excel download and the browser rendering of four of the five pages were checked by API, not by
  clicking through. Disability is not collected, so equity cannot report it. Scheduled/e-mailed reports and a custom
  report builder are out of scope.
- E-mail goes to the console backend; nothing is sent. Invites can go to any address a staff member types.
- Staff are not notified when an employer asks to publish. No "forgot password" screen on the login page (the reset
  endpoints exist). No e-mail on password change.
- Not checked: restoring an employer whose name now duplicates a live one; dark mode, mobile and the steward view
  were only spot-checked; the official CAP-YEI SVG logo (PNG in use); employer activity text shows "county ids".
- The statuses "Done" in older notes meant built, not signed off: the M2 review (`docs/m2-review.md`) awaits the
  product owner's sign-off.
- Client questions still to put: D-015 (lawful basis, notice text, retention), D-004 follow-up (MIS extract), D-001
  (is YDM in scope), the 90-day review cadence and the 5/5/5 minimums, and approval of the dashboard definitions.

**Suggested next steps, in order:** (1) the user walks `docs/walkthrough.html` and reports failures; fix those;
(2) T-068 rule simulation in CI; (3) T-077 hardening, including the MFA bypass; (4) T-069 once definitions are
approved; (5) T-076 environments once hosting is decided; (6) learner phase 3 if approved.

---

## 7. Working rules

**Data and security**
- No real trainee data in the repo or in development, ever (SEC-14). Synthetic data only; spreadsheets are
  git-ignored. Test credentials live only in `backend/scripts/seed_dev.py`.
- Never put a password or `DATABASE_URL` in chat, a commit or a doc.
- The repo stays under the owner's account until D-032 is decided; then it moves to the CAP-YEI organisation with
  branch protection and required checks.

**Frontend (Metronic 9 only)**
- Reuse order: shared component, then Metronic `components/ui/*`, then a new shared component. No other UI kit.
- Every page uses `PageHeader`; lists use `DataCard`, `SearchBox`, `FilterSelect`, `Pager`. Every list row has a
  `RowActions` menu (View, Edit, Archive/Restore) shown only if `can(...)`; lists have bulk select and `BulkBar`.
  Detail pages put Edit and Archive/Restore in the header actions.
- Forms are in a modal, with searchable selects (never native `<select>`); edit forms send only changed fields.
- Real backend data only; every data region has loading, empty and error states (`components/states.tsx`); confirm
  destructive actions with `ConfirmDialog`; responsive and accessible.
- Screenshots only for visual questions (scale 0.5); prefer reading page text.

**Working agreement with the product owner**
- "next" means do the next planned task and explain as you go (teach the Django/React concepts); end each task with
  how-to-test steps and the next tasks.
- A feature is not done until its Help centre guide is added or updated.
- One commit per task on `main`, with the `Co-Authored-By` trailer. Ask before pushing. Push needs `gh` credentials
  (`gh auth setup-git`).
- Append to the handoff log whenever work lands or a decision is made.
- "Start the app / localhost" always means the Postgres dev database (section 2).
