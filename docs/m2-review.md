# M2 review (T-052) and iteration QA (T-051)

Prepared 2026-11-12 for the product owner and CAP-YEI sponsor. Covers the M2 foundations phase
(W5-W8 in the plan). Evidence is the repository on `main`; nothing here uses real trainee data.

## 1. What is built and demonstrable

| Area | Demo path | Tasks |
|---|---|---|
| Sign-in, roles, record scope, audit trail | Administration → Staff accounts; any record's activity tab | T-034..T-037 |
| Reference data managed in the app | Administration → Programmes, Cohorts, Courses, Cohort courses, Training institutions, Sectors, Counties, Sub-counties, Wards | T-039, T-057 |
| Kenya geography loaded by seeders (47 counties, 290 sub-counties, 1,448 wards) | Add youth → Home and contact → pick a county, then sub-county, then ward | T-057 |
| Import wizard, duplicates and merge, reconciliation, Go Blue dry run | Import participants | T-040..T-042, T-053, T-059, T-086 |
| Youth directory, profile, edit every field, Add youth wizard | Youth → Add youth | T-043, T-058 |
| Employers, opportunities, employer de-duplication, placement import | Employers, Opportunities | T-044, T-045, T-087 |
| Referral workflow with stage history and corrections | Referrals | T-046 |
| Rules engine and versioning (draft, review, approve, activate) | Rules | T-047 |
| Three draft rule sets, one per module, with every undecided value shown | Rules → open a draft version | T-048 |

## 2. Quality evidence (T-051)

Run on 2026-11-12 against `main` plus the geography change:

- Backend: full pytest suite passes; ruff clean; import-linter 15 contracts kept; no missing
  migrations; OpenAPI validates.
- Frontend: production build succeeds; eslint and vitest (9 tests) pass; tsc is clean except
  pre-existing errors in `users-page.tsx` and `components/ui/*` (not in code written for M2).
- Authorisation: `tests/test_authz_matrix.py` requires every route to be classified.
- Browser checks this iteration: cohorts page; searchable select inside a dialog; Mombasa →
  Changamwe → 5 wards cascade in the Add youth wizard.

Gaps against T-050 (test framework), honestly stated: pytest, factories-style seeders, the
authorisation matrix harness and the dev synthetic data exist. **Not yet in place:** Playwright
end-to-end tests, automated axe accessibility checks, and a synthetic data generator covering all
entities. Not manually tested: dark mode, mobile layout, the add/edit/retire round trip on every
new reference page, restoring an employer whose name now duplicates a live one.

## 3. Decisions and RAID

Working defaults the code uses until CAP-YEI answers (not flipped in the register by us):

| Item | Working default | Needed from |
|---|---|---|
| D-009 | Administrator alone approves rule versions | Product owner |
| D-037 | Proposed referral stages and 12 reason codes | CAP-YEI |
| D-007 | Trainee applications not modelled | CAP-YEI |
| D-008, D-013, D-026, D-028 | Every rule threshold, weight and count is an undecided parameter | CAP-YEI / practitioners |
| D-064, D-066 | Employer status mapping defaults | CAP-YEI |
| D-001 | No YDM factor in matching | CAP-YEI |

New this iteration:
- **Sub-county level uses the 290 IEBC constituencies** because wards are published under them;
  the 1,448 wards come from a public MIT-licensed dataset (`kenya-locations`), two short of the
  1,450 often quoted. Official sub-county names (307) differ in about 77 places. Product owner to
  confirm this is acceptable or supply an authoritative list.
- Production Data steward role needs `config.view` added by an administrator (Roles page).
- Remove the DEBUG-only MFA bypass before go-live.

## 4. Retrospective

- Went well: row actions, archive-not-delete and the shared form modal kept new screens
  consistent; one generic reference page replaced a sector-only page.
- Slowed us: long chat sessions lost context twice; a port clash with another local project.
- Change: finish T-050 gaps early in M3 so each Month 3 module ships with end-to-end and
  accessibility checks.

## 5. Sign-off requested

Product owner accepts the demonstrated stories for M2, and answers D-009 and D-037 so the rules
and referral stages can leave "working default" status.
