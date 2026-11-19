# PI 360: project status and working rules

Living document. Update it when a phase closes or a rule changes. The plan is in `../planning/`
(task IDs `T-xxx`, decisions `D-xxx`); the per-session history is in the Obsidian handoff log
`Claude Handoff/capyei-pi360.md`. Last updated: 2026-11-12 (evening).

## 1. Where we are

Plan phase **M2 (foundations, W5-W8) is mostly built; the build has run ahead of the calendar** on
the import, directory and admin tooling. Pushed `main` is at `github.com/samgithae/capyei_PI360`
(last push 36c7c82). Newer work, listed under "Built, not yet committed" below, is local only.

| Area | State | Tasks |
|---|---|---|
| Skeleton, CI, Metronic shell, auth (MFA, off in debug), RBAC + record scope, audit trail, user admin | Done | T-019, T-032, T-034..T-037, T-141, T-143 |
| Reference data, flags, protected settings | Done | T-038, T-039, T-057 |
| Import pipeline + wizard, duplicates/merge, reconciliation, Go Blue dry run, extra data, cohort defaults | Done | T-040..T-042, T-053, T-059, T-086, T-142 |
| Participant directory and profile, **edit every field** (core, enrollments, residence, contacts) | Done | T-043, T-058 |
| Employers, opportunities (+ expiry job) | Done | T-044, T-045 |
| Employer clustering and placement import, status mapping, promote extra data | Done (D-064, D-066 await CAP-YEI) | T-087 |
| **Archive/restore** (soft delete) for participants, employers, opportunities; admin parity with steward | Done | this phase |
| Row actions + bulk select on /youth, /opportunities, /employers | Done | this phase |
| Referral workflow (stages, reason codes, corrections, reassign) | Done; stage list and reason codes await D-037 | T-046 |
| Rules engine and rule versions (draft, review, approve, activate; a version in force is never edited; every step audited) | Done; D-009: the Administrator approves for now (holds both rule permissions) | T-047 |
| Initial rule configuration (three draft rule sets, one per module, loaded by `load_initial_rules`) | Done as drafts; every value awaits D-008, D-009, D-013, D-026, D-028 | T-048 |
| Reference admin pages for every list (programmes, cohorts, courses, counties, sub-counties, wards...); Kenya geography seeded (47 / 290 / 1,448); searchable selects | Done | T-057 |
| YDM assessment capture | Not started, optional, gated | T-049 |
| Module B interim form: Suggested youth shows "Preferred: X of Y" and ranks by it, no percentage | Built, uncommitted; weights await D-009 | T-060 |
| Module C evidence: employer "Referral evidence" card (counts, period, source, "Insufficient evidence" under the minimum, no overall rating). Retention after placement is calculated from completed check-ins at the early retention point, the latest early step of the follow-up schedule (90 d by default), so changing the schedule moves it; due-but-unchecked shown apart, never counted as lost. Employer feedback is logged by officers on the employer page (1 to 5 rating, required source: call, visit, e-mail or meeting) and shown as a percentage rated positive only above an admin-set minimum (`employer.min_feedback`, `employer.positive_rating`); retention has its own minimum (`employer.min_retention_checks`); rule review cadence is `rules.review_days` (D-009 working value) | Built and committed; minimum and period are admin settings | T-067 |
| Module A support priority: /support queue (unsuccessful referrals, stalled referral, ready-but-never-referred) with "Mark reviewed" that pauses a flag | Built, uncommitted; documents and retention flags not captured yet | T-063 |
| Rules > Settings: admin-editable numbers (defaults in code, changes audited) behind A and C | Built, uncommitted; D-013 and D-028 decided (starting values in code, editable); D-026 values unapproved | T-063, T-067 |
| **Programme dashboard** at `/`: KPI tiles, funnel, gender and placement, referral pipeline, monthly trend, age, county, needs-attention list, metric definitions; every number opens the list of records it counts (`/dashboard/list`) | Built, uncommitted; P0 and part of P1. Definitions marked "working" await CAP-YEI approval. Retention, training completion, skills demand, predictive, staff productivity not built | T-069, T-070 |
| Case management (`/cases`) and placements (`/placements`): interventions, queues, verification, placement episodes | Committed locally (542a16a, not pushed) | T-064, T-065 |
| Follow-up scheduling (`/followups`, Administration > Follow-up schedule): configurable steps, check-ins made when a placement with a start date is recorded or verified, attempts, response and evidence, next action. A schedule change affects new placements only | Built and pushed (`9b797c5`). Default intervals (30 d, 90 d, 6/12/24 months) decided (D-012, D-028) and editable by an administrator | T-066 |
| Record placement from a referral: on a Selected or Placed referral the button opens the placement form with youth, employer and role filled in (a referral never creates a placement by itself) | Built and committed (e281025) | T-065 |
| Duplicate-placement warning: recording a placement for a youth who already has a running one with the same employer (register id, or the typed name ignoring case and spacing) returns a 409 `possible_duplicate`; the dialog shows it with "record anyway", which resends with `confirm_duplicate`. Ended spells and episodes created with an end date never trigger it. Help guides updated | Built and committed (e281025) | T-065 |
| Data retention (`/administration/retention`, `run_retention` command): per-class period + written basis + separate approval; first class is imported source rows (values cleared N days after the batch's reconciliation sign-off, keeping counts, errors, cohort code, hashes). Dry run by default; applied runs need confirmation; every run recorded and audited with counts only. Participant, audit, placement and follow-up data are not covered yet | Built and committed (b55b9b4); no period is set or approved (nothing is cleared) until D-015; scheduling the command is deployment work (T-076) | T-073 |
| Data quality and MIS corrections (`/data-quality`, permission `dataquality.review`, Administrator and Data steward): nine rules list the youth that fail them (no county, unknown gender, missing or out-of-range age, unknown status, no contact, no MIS number, reversed dates, single name). Fixes to name, gender, age, county or enrolment status on youth that came from the MIS are kept as corrections (was, now, who, when). They can be exported for whoever updates the MIS (table `corrections`, field picker, `exports.identifiable`). An import never overwrites an open correction: the same value closes it, a different value is held back and shown for review (Keep my fix / Accept MIS value). Help guide added | Committed (cbc9a7c). Age bounds 14 to 35 are provisional. D-025 option (a) is the user's working basis, not yet marked in the register | T-074 |
| Privacy notice and consent (minimum): each youth has a consent status (not recorded, given, declined, withdrawn), the privacy notice version and the date, set from a card on the Programme & Account tab by anyone who can edit youth (`PUT participants/<id>/consent`, audited with no personal values). Youth with no consent show a No consent badge in the Youth list; the three fields can be ticked in the youth export. Imported youth start as not recorded. Only a flag: nothing is blocked. Behind the `consent_tracking` feature flag, off by default; an administrator turns it on under Administration, Youth records (audited). While off, the card, badge, API fields and export fields are all absent. Help guide added | Built, not committed. Statuses and wording are provisional on D-015 (CAP-YEI data protection lead undecided). Not built, to add on request: a list filter, a data-quality rule, blocking exports or referrals, withdrawal handling, per-purpose consent | T-054 |
| Search and duplicate warnings: Add youth warns of likely duplicates (same name, reordered words, small spelling difference; phone and birth date sharpen it, never shown) at the name step and again at Review; the directory search takes words in any order, enrollment numbers and source IDs, and falls back to near-spellings. Portable matching, no `pg_trgm` index yet | Built, uncommitted. Thresholds in `participants/similar.py` are proposals pending D-004 | T-055 |
| Table export (`POST /exports/table/<table>`, tables: youth, employers, opportunities, referrals, placements, followups): an **Export** button on each list's toolbar downloads exactly the rows the filters select as CSV or Excel, with the table's columns. **Every table** lets the person choose fields first (`GET /exports/fields/<table>`; body `fields`, default all; one catalogue per table in `reporting/exports.py`, youth's in `participants/export_fields.py`). Youth fields: identity, contact, residence, programme/cohort, education, skills, work experience, readiness, plus referrals and placements, one row per youth with related records joined by "; " (catalogue in `participants/export_fields.py`). This reverses the earlier rule that youth exports never hold phone, email, address or date of birth: they are offered, ticked by default, flagged Sensitive, and covered by the grant and purpose; the chosen field keys are logged. Never offered: staff/verification notes, free-text duties and achievements, photos; no national ID is stored. Employers and opportunities hold no youth names; Company contacts (employers) is the other Sensitive field, ticked by default; the other tables never hold contact details, notes or evidence. Each list's filter is one shared function used by both the list and the export. Cases is a work queue and has no export. Formula-like names escaped. Needs the grant-only `exports.identifiable` plus a stated purpose; the file is streamed and not stored; `ExportLog` row and audit entry hold filters, count, purpose and chosen field keys, no names or values. Administration > Access grants (`/identity/grants`, needs `identity.manage_roles`) lets an administrator grant or withdraw restricted permissions per person, with purpose and an end date (max 365 days). The old de-identified backend (`exports.deidentified`, `/exports` API, `purge_exports`, Rules group E) is kept without UI until D-045 | Built (Youth committed in 9b6a82f; the picker on the other five tables in 36e30e7); scheduling `purge_exports` is deployment work (T-076) | T-071 |
| End-to-end tests (`frontend/e2e`, `npm run e2e`; Playwright, own ports 8020/5190, throwaway SQLite seeded by `seed_dev.py`): sign in and out, youth search and scope, data quality, consent setting; plus an axe scan (WCAG 2 A/AA) of the sign-in page, 16 signed-in screens and each tab of a youth page, failing on serious or critical findings. Fixed along the way: sidebar menu structure, section-label contrast, account button name, dashboard progress bars and pie chart. CI job `e2e` | Built, uncommitted | T-050 |

**Built, not yet committed (working tree, 2026-11-12):** the Module A/B/C rows above; the rules
engine no longer needs a "product owner confirmation" tick (a parameter is unapproved only when it
has no value); the rule version page restructured into a facts strip with Factors, Parameters and
History tabs; Help guides for the new pages. Verified: full backend run (no failures), ruff,
lint-imports (16 contracts kept), regenerated `openapi.yaml`, frontend tsc/eslint/vitest (36),
dev DB migrated. Not verified: the new pages in a browser as a full flow, Edit draft and Set value
after the page restructure. YDM (D-001) stays out. Local commits made earlier (learner portal
phases 1-2, grades, youth self-edit) are also unpushed; ask before pushing.

Open items: remove the DEBUG-only MFA bypass before go-live; CI on the latest pushes unchecked;
dark mode / mobile / steward-view only spot-checked; restoring an employer whose name now
duplicates a live one is not checked; official CAP-YEI SVG logo (PNG in use).

## 2. Rules we have set

**Data and security**
- No real trainee data in the repo or dev, ever. Synthetic data only; spreadsheets are git-ignored.
- Every permission is enforced on the API; the UI only hides what the API forbids.
- Roles are database data; permissions are a code-defined catalogue (`apps/identity/catalogue.py`).
  Every route must be classified in `tests/test_authz_matrix.py`.
- Session cookie + CSRF; no tokens in browser storage. Test credentials live only in
  `backend/scripts/seed_dev.py`.
- Audit every write. Audit entries for contacts record kinds and flags, never values.

**Architecture**
- `apps.api` must not import domain modules; domain modules import only other modules'
  `services` (never `models`). Enforced by import-linter/architecture tests.
- API changes regenerate and commit `backend/openapi.yaml`
  (`spectacular --validate --fail-on-warn`). Serializer class names are unique across apps.

**Delete means archive**
- No hard deletes of business records. "Delete" is an archive (`archived_at`), restorable by an
  administrator, gated by `records.archive`, audited as `<type>.archived` / `.restored`.
- Lists hide archived rows unless "Show archived" is on. An archived employer hides its
  opportunities. Archived employers are ignored by duplicate checks and pickers and cannot receive
  new opportunities until restored.
- Archiving always asks for confirmation (`ConfirmDialog`).

**Frontend (Metronic 9 only)**
- Metronic 9.5 is the single design system: reuse order is shared component -> Metronic
  `components/ui/*` -> new shared component. No other UI kit. Details: `frontend/UI-STANDARDS.md`.
- Every page uses `PageHeader`; lists use `DataCard`, `SearchBox`, `FilterSelect`, `Pager`.
- **Action buttons:** every list row has a `RowActions` menu (View, Edit, Archive/Restore), each shown
  only if `can(...)`. Lists have `SelectAllHead` / `RowCheckbox` and a `BulkBar` for bulk archive.
  Detail pages put Edit and Archive/Restore in the `PageHeader` actions.
- Forms are in a modal (`FormModal`/dialog), not native `<select>`; edit forms send only changed fields.
- Real backend data only; every data region has loading, empty and error states; confirm
  destructive actions; responsive and accessible.
- Screenshots only for visual questions (scale 0.5); prefer reading page text.

**Working agreement**
- "next" = do the next planned task. Explain as we go (teach Django/React), and end each task with
  how-to-test steps and the next tasks.
- One commit per task on `main`, trailer `Co-Authored-By`. Run before commit: backend
  `pytest`, `ruff check`, `ruff format`; frontend `prettier --write src`, `tsc`, `lint`, `vitest`.
- Append to the handoff log whenever work lands or a decision is made.
- Decisions that belong to CAP-YEI stay "working decisions" in the code and docs; the register
  (`planning/registers/decisions.csv`) is not flipped by us.

**Dashboard (2026-11-12):** `apps/reporting` builds named metrics, each a set of records, so a tile and
its list cannot disagree; scope and list permissions apply to both. Endpoints `reporting/dashboard`
and `reporting/drilldown`. Placed = a placement mapped as placed, or a referral that reached Placed.

## 3. Next phase

**Finish M2: the intelligence foundation, then start M3.** See section 4 of the chat hand-off or
`../planning/01_Implementation_Plan.md` §5 and `02_WBS.md`.

1. **T-050 gaps**: none open. Playwright e2e (`frontend/e2e`, `npm run e2e`) and axe accessibility scans of every main screen run in CI. A synthetic data generator was dropped by decision (manual testing; `backend/scripts/seed_dev.py` supplies the dev data). T-051 QA run once: see `docs/m2-review.md`.
2. **T-052 M2 review**: `docs/m2-review.md` written; awaiting product owner sign-off.
3. Then M3 (I05): T-064 interventions/case queues, T-065 placements and employment episodes,
   T-054 consent fields (minimum built on the provisional D-015 basis, behind an off-by-default setting); T-055 duplicate warnings is built. The interim forms of T-060 (Module B), T-063
   (Module A) and T-067 (Module C) are built; their final scoring waits for the decisions below.
4. **Decisions (answered 19 Nov 2026, relayed by the implementer):** decided: D-009 (the
   Administrator approves rule versions for now; review cadence still to set), D-012 (follow-up
   schedule 30 d, 90 d, 6/12/24 months), D-013 (show with count, hide below the minimum sample),
   D-028 (early follow-up 30 d, early retention 90 d), D-037 (keep current stages, editable reason
   codes). Proposed, not final: D-026 (starting values, marked unapproved until the placement lead
   approves), D-015 (provisional basis; the data protection lead has not answered and production
   import stays blocked), D-045 (keep current export rules). Every figure is an admin setting or
   editable data, never hard-coded. Still to set: the D-009 review cadence; D-004 not asked.

Done in this phase: T-046 referral workflow, T-047 rules engine and versioning, T-048 initial
draft rules.

## 4. Learner portal roadmap (youth as a personal placement tracker)

- **Phase 1 (done, 2026-11):** dashboard at /me, My opportunities list and detail, built from
  existing referral data. Youth never see scores, rejection reasons or staff notes.
- **Phase 2 (built, awaiting commit):** interview details, My placement page, in-app notifications.
- **Phase 3 (later, when we have the data): support issues and follow-ups. New module, needs
  design.** Design draft: `docs/learner-support-design.md`.
  - Support tickets with a reference number, category, status, assigned officer and message history.
  - Sensitive categories (safety, harassment) need restricted access and must never reach the
    employer.
  - Follow-ups at 1 week, 30, 60 and 90 days and 6 months, with a short check-in the learner
    answers. The data they produce is the retention outcome.
  - Open before building: who owns tickets, phone check-ins, retention period, and a reliable
    placement start date.
