# PI 360: project status and working rules

Living document. Update it when a phase closes or a rule changes. The plan is in `../planning/`
(task IDs `T-xxx`, decisions `D-xxx`); the per-session history is in the Obsidian handoff log
`Claude Handoff/capyei-pi360.md`. Last updated: 2026-11-12.

## 1. Where we are

Plan phase **M2 (foundations, W5-W8) is mostly built; the build has run ahead of the calendar** on
the import, directory and admin tooling. Everything below is on `main` at
`github.com/samgithae/capyei_PI360`.

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
| Rules engine and rule versions (draft, review, approve, activate; a version in force is never edited; every step audited) | Done; who approves awaits D-009 (Administrator holds both rule permissions for now) | T-047 |
| Initial rule configuration (three draft rule sets, one per module, loaded by `load_initial_rules`) | Done as drafts; every value awaits D-008, D-009, D-013, D-026, D-028 | T-048 |
| Reference admin pages for every list (programmes, cohorts, courses, counties, sub-counties, wards...); Kenya geography seeded (47 / 290 / 1,448); searchable selects | Done | T-057 |
| YDM assessment capture | Not started, optional, gated | T-049 |
| Modules A/B/C, dashboard, exports, case management, follow-up | Not started (M3) | T-060..T-071 |

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

## 3. Next phase

**Finish M2: the intelligence foundation, then start M3.** See section 4 of the chat hand-off or
`../planning/01_Implementation_Plan.md` §5 and `02_WBS.md`.

1. **T-050 gaps**: Playwright e2e, axe checks, synthetic data generator (not started). T-051 QA run once: see `docs/m2-review.md`.
2. **T-052 M2 review**: `docs/m2-review.md` written; awaiting product owner sign-off.
3. Then M3 (I05): T-064 interventions/case queues, T-065 placements and employment episodes,
   T-060 compatibility engine (Module B), T-063 support priority (Module A), T-067 employer
   reliability (Module C), T-054/T-055 consent and duplicate warnings.

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
