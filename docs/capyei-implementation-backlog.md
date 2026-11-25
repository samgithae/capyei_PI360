# CAPYEI meeting of 23 November 2026: implementation backlog

**PI360** · Planning document · 23 Nov 2026 · Status: proposal, nothing started. **Revised after CAP-YEI's answers of 23 Nov 2026**: read "Changes after CAP-YEI's answers" below first.

This is the companion to `docs/capyei-meeting-implementation-plan.md` (the plan), `docs/capyei-data-model-changes.md` (the data model) and `docs/capyei-decision-register.md` (decisions D-070 to D-090).

**How to read a task**

- **Priority:** Critical = needed for safe pilot use; High = meeting requirement with clear value; Medium = useful, can follow; Low = optional.
- **Complexity:** Small (≤1.5 d), Medium (2–3 d), Large (3–4 d), Very Large (>4 d).
- **Estimates** are one developer's working days, including tests and the help-guide update. "±" marks uncertainty. A task marked **Blocked** cannot start until the named decision is recorded; its estimate assumes the recommended option.
- **Definition of Done for every task** (not repeated below):
  - code and tests pass `make test`, import-linter and `ruff`;
  - every new route is in `tests/test_authz_matrix.py` and has `required_permission`;
  - `openapi.yaml` is regenerated;
  - audit events are recorded with keys only;
  - UI follows `frontend/UI-STANDARDS.md` (Metronic 9, existing components);
  - the relevant help guide in `frontend/src/pages/help/` is added or updated;
  - all fixtures and screenshots use synthetic data.

## Changes after CAP-YEI's answers (23 Nov 2026)

The answers are recorded in `docs/capyei-decision-register.md` §0; the analysis is in `docs/capyei-answers-impact-assessment.md`. The task texts further down are unchanged. Where they differ from this section, **this section wins**. Work in the order of the revised phases (impact assessment §5). Tasks marked **Blocked** on a decision that is now Decided are unblocked.

**Changed tasks**

| Task | Change | Source |
|---|---|---|
| NEW-004, NEW-005 | **Superseded by NEW-069** (rename everywhere). No API alias. | B1, D-070 |
| NEW-006 – 008 | Unblocked. Courses become one shared list; the label stays alongside the structured cohort fields; youth with no project are allowed. | B2, B4 |
| NEW-010 – 013 | Unblocked. Bulk outcomes are Verified or Needs Reassessment only; one method and note per batch; Administrators, Placement and Project officers. | B6–B8 |
| NEW-015, NEW-016 | Employment never changes availability. Never-placed youth default to Open. Youth marked Closed are left out of suggestions. Default for already-placed youth is clarification C-1. | B9, B12 |
| NEW-019, NEW-020 | One instrument, 6 competencies, 26 criteria. Scale 1 Poor … 5 Excellent. Competency = average of completed criteria; overall = average of the 6; blanks excluded; show "n of 26 completed"; no completeness threshold; history kept. | B13, B15 |
| NEW-024 | Recording is for **Administrators and Placement officers** only (not Assessors, trainers or Project officers). No approval step until B16 approval is answered. | B16, B37 |
| NEW-026 – 028 | Scale 1 Very Poor … 5 Excellent; 1–2 negative, 3 neutral, 4–5 positive. Alert at ≥3 ratings with average below 3.0, or any single 1. Outcomes Monitor or Ignore. No suspension. B19 criteria and employer aggregates (A6 minimum) stay open. | B19–B23, A6 |
| NEW-030 | Build B-COMP with its **weight unset** (off) until B18's weight is given. | B18 |
| NEW-033 | **Superseded by NEW-075** (quality warning, not a ranking column). | B24 |
| NEW-034 – 037 | 8 employment types and 8 leaving reasons as given; exact salary **and** band; retention at 3, 6 and 12 months, split same employer / other employer. | B25, B26, A3 |
| NEW-039 | Plus NEW-076 (confidentiality per record). | A4 |
| NEW-040 – 043 | Yes / No with an optional description; no "Prefer not to say"; placed after Gender (B30 still to confirm); all access logged (NEW-073). Go Blue historical import allowed (A1), only after D-090. **NEW-040, NEW-041 (edit page) and NEW-073 built 24 Nov 2026:** `Participant.disability` (not_recorded / yes / no) with an optional description (only kept with Yes), `disability_recorded_at`, `disability_source`; own route `participants/<id>/disability` (404 while flag `participants.disability` is off, which it is); permission `participants.view_disability` is in **no default role**; every read and change writes `participant.disability_viewed` / `_changed` to the audit log without the answer; never in the detail, list, export or CV. **Not built:** the add-youth form (record it on the edit page after creating), NEW-042 import mapping (waits for D-090) and NEW-043 reports (waits for D-089). The "after Gender" position (B30) is still unconfirmed: the card sits under Personal details. | A1, B30–B32 |
| NEW-044 – 049 | **No officer approval.** The account works after e-mail or phone verification (phone mandatory after the pilot). NEW-046 becomes a duplicate-review and merge queue. Rejected requests are kept until an Administrator deletes them. Consent wording from A5. | A5, B33, B34 |
| NEW-050 – 051 | Four triggers confirmed; any officer in scope marks Reviewed; blocks nothing. **NEW-050 built 24 Nov 2026 (backend):** `Participant.review_state` (none / needs_review / reviewed), `review_reason` (self_registration, self_edit, import_change, officer_flag), `review_since`, and an append-only `ReviewEvent` history (migration 0014; existing youth start at none). Triggers: a sign-up linked to a record; the youth changing name, gender, date of birth or county (contacts and residence do not trigger); an import update changing name, gender, age or county; an officer flag with a required note. Endpoints: `GET/POST/DELETE participants/<id>/review` (history, flag, mark reviewed) and `POST participants/review/mark` (bulk), `participants.edit` within scope; the participant detail carries `review`. Audit holds the reason code, never the note. Blocks nothing; the youth portal does not show it. **NEW-051 built 24 Nov 2026:** `GET /participants?review=needs_review` filter and a `review` field on each row; directory has an Any-review-state filter, a Needs review badge and a bulk Mark reviewed button for anyone with `participants.edit`; the youth page has a review strip (reason, Mark reviewed with optional note, Flag for review with required reason, history); help guide `review-list`. Not built: a review count on the dashboard, an export column, filtering by reason; D-084 stays as recorded. | B35, B36 |
| NEW-054 | Not built: the portal shows **referred opportunities only** (already the case). | B42 |
| NEW-056 – 060 | Project officer = Placement officer limited to their projects; shared youth visible to both; import **and identifiable export** within scope (how to grant it: C-2). Unassigned youth: all-scope roles plus NEW-072. | B37–B40 |
| NEW-058 | Not built: employers and opportunities stay shared. | B41 |
| NEW-062 | Draft now exists: `docs/capyei-metric-definitions.md`. Still needs CAP-YEI approval (B43). | B43 |

**New tasks**

| ID | Task | Est. | Depends on |
|---|---|---|---|
| NEW-069 | **Rename Programme → Project everywhere**: RenameModel/RenameField migrations (no drop), scope kind data migration, API paths and fields in one release, frontend, help guides, OpenAPI; imports accept both header names; audit history not rewritten. Replaces NEW-004/005. **Built 23 Nov 2026** (migrations configuration 0011, participants 0012, identity 0011, imports 0007; reversible, tested both ways); dev DB migrated; awaiting staff check in the app. | 9 d ±2 | — (first) |
| NEW-070 | **One active placement per youth**: service refusal, partial unique constraint, pre-check count, "changed employer" ends the old placement; import behaviour per C-3 (proposal: hold for review). **Built 23 Nov 2026**: service rule per youth across enrollments (row lock), DB partial unique constraint per enrollment (placements 0006, refuses to run if clashes exist; dev DB had none), `POST /placements/{id}/change-employer` (atomic end + record), record form shows the refusal. Import holds a second running row for review — **provisional working rule, C-3 still open**. Known gaps: a duplicate-youth merge can still leave two running placements on different enrollments; metric 8 still needs the `previous` link (NEW-035). D-081 status unchanged. Awaiting staff check in the app. | 2.5 d | NEW-069 |
| NEW-071 | **Self-employment outcome** with its 7 fields, counted as a separate outcome. **Built 23 Nov 2026:** business activity, operational status, evidence and monthly income added to the placement (name, date started and verification reuse existing fields); refused on other pathways; income read/write only with grant-only `restricted.view_background` and kept out of the audit values. Operational status list is **provisional** (CAP-YEI gave none). Link to the NEW-034 follow-up outcome still pending. D-080 status unchanged; production use of income stays gated by D-090. | 2 d | NEW-034 |
| NEW-072 | **Self-Registration Queue** for youth with no project, visible to all-scope roles. **Built 24 Nov 2026 (with the NEW-044 model, `portal.RegistrationRequest`):** staff with `duplicates.review` list, filter, search and reject requests (reason required, audited); an Administrator (`config.manage`) deletes rejected or expired ones. Behind the off-by-default flag `portal.self_registration` (404 when off). Hashes only, no raw IP. **NEW-045 built 24 Nov 2026:** `POST /registrations/submit` and `/registrations/verify` (public, CSRF-protected, 404 when the flag is off): identical reply for new, repeat and settled sign-ups; 10 per hour per IP (`API_THROTTLE_REGISTER`) and 3 per hour per e-mail; one-use e-mail link; a repeat sign-up before verifying just re-sends a link. **Gaps:** e-mail verification only (no SMS channel, so phone is stored unverified and the OTP columns are unused); no status endpoint; **NEW-049 built 24 Nov 2026 (minimal):** public `/register` form (name, date of birth, e-mail, optional phone, programme and enrolment number, consent tick with DRAFT wording) and `/register/verify` landing page; same "check your e-mail" reply every time, "not open yet" while the flag is off. **NEW-046 built 24 Nov 2026 (core):** `GET /registrations/<id>/matches` (similar people the officer may see; sets `possible_duplicate`), `POST .../link` (reason required; never creates; one sign-up per record) and `POST .../create` (needs `participants.edit`; refused with `confirm_similar` when someone similar exists; copies name, date of birth, gender, contacts only; claimed programme not turned into an enrolment); all audited; Review panel on the queue page. **NEW-047 built 24 Nov 2026:** on create or link the usual youth invite is e-mailed to the address the youth confirmed (`send_invite(..., verified_address=True)`; same activation, one account per record; none if the record already has an active account; none for an unconfirmed address; a mail failure keeps the decision and reports `invite.reason`); the queue page shows the result. A linked sign-up's e-mail is not copied onto the existing record. Not built in NEW-046: automatic move to "Needs review" (NEW-050), matching on e-mail, scope restriction beyond the permission. Not built in NEW-049: status page, sign-in link after verifying, language choices, mobile-first polish, CAPTCHA. **Not built:** approve or link and the duplicate check (NEW-046/047), the "Needs Review (possible duplicate)" state (NEW-050), and any all-scope restriction beyond the permission. D-083 consent wording and D-090 stay unapproved. | 2 d | NEW-044 |
| NEW-073 | **Disability access log**: every read and change recorded (no values in the audit row). | 1.5 d | NEW-040 |
| NEW-074 | **Go Blue course list 001–007** (including SIYB) as shared courses, from the synthetic/redacted sample only. | 1 d | NEW-006 |
| NEW-075 | **Employer-quality warning** in suggestions; Inactive employers excluded (C-4); never overrides mandatory requirements; no penalty size until set. Replaces NEW-033. **Built 25 Nov 2026** (NEW-027 was not built, so it uses the existing feedback ratings): `employer_quality` block on `GET opportunities/<id>/suggestions` and a yellow warning on Suggested youth when, in the period, there are at least `employer.warn_min_ratings` (3) ratings averaging below `employer.warn_below_average` (3) or any single rating of 1 (working values from the alert rule, both editable on Rules settings). Counts only, no comments. It changes neither eligibility nor order and applies no penalty (size still open). An Inactive employer gets no suggestions. Not built: a per-criterion basis (needs NEW-026/027). | 1.5 d | NEW-027 |
| NEW-076 | **Exit-feedback confidentiality per record**, with an admin default (ON); changing it affects new submissions only. | 1 d | NEW-039 |
| NEW-077 | **Duplicate merge with conflict resolution** (B28 kept on merge). **Built 23 Nov 2026:** steward picks the survivor; gaps filled automatically, real differences need an explicit choice; critical conflicts (two running placements, same course offering, two active referrals to one opportunity, two portal accounts) save the merge as *pending resolution* and move nothing; an officer with placements.edit ends one placement or marks it *recorded twice* (kept, linked), with a reason, date and name recorded; merge completes only when none remain. Nothing is closed, deleted or overwritten automatically; referrals and portal accounts now move and come back on undo; audit keeps both ids. Backend-enforced `duplicates.merge`. Help guide "Merge two records of the same youth". Which other conflicts count as critical is a proposal for CAP-YEI to confirm. | 3 d | NEW-070 |

**Effect on the total:** about **+12.5 days**, so roughly **≈ 169 dev-days** (±20 %). Mostly from the full rename (+4 d net) and the new tasks.

## Summary

| Epic | Tasks | Days (approx.) |
|---|---|---|
| X Cross-cutting setup | NEW-001 – 003 | 4.5 |
| A Projects and courses | NEW-004 – 009 | 14.5 |
| B Bulk skills verification | NEW-010 – 013 | 7.5 |
| C Open for Opportunities | NEW-014 – 018 | 8.5 |
| D1 Trainer competency assessment | NEW-019 – 025 | 19.5 |
| D2 Employer ratings | NEW-026 – 029 | 10.5 |
| E Matching | NEW-030 – 033 | 9 |
| F Follow-up and employment history | NEW-034 – 038 | 11.5 |
| G Exit feedback | NEW-039 | 2.5 |
| H Disability | NEW-040 – 043 | 7.5 |
| I Self-registration | NEW-044 – 049 | 16 |
| J Review status | NEW-050 – 051 | 4.5 |
| K Youth portal | NEW-052 – 055 | 9.5 |
| L Project isolation | NEW-056 – 061 | 12.5 |
| M Reporting | NEW-062 – 064 | 8 |
| Cross-cutting close | NEW-065 – 068 | 10 |
| **Total** | **68** | **≈ 156 dev-days** (±20 %) |

---

## Epic X: Cross-cutting setup

### PI360-NEW-001: Decision pack and DPIA addendum
- **Description:** Put D-070 to D-090 to CAP-YEI and the DPO. Add the decisions to `planning/registers/decisions.csv` with status "open" and record each answer as it arrives.
- **Existing:** `planning/registers/decisions.csv` (last D-069); `docs/capyei-decision-register.md`.
- **Proposed changes:** Add register rows only. Prepare the DPIA addendum covering disability, self-registration, trainer assessments, exit feedback and remuneration. No code.
- **Dependencies:** none.
- **Priority:** Critical · **Complexity:** Medium · **Estimate:** 2 d (calendar time depends on CAP-YEI).
- **Acceptance criteria:** Every D-070–D-090 has an owner and a due date. No status is changed without a recorded answer.
- **Tests:** Not applicable (document review).

### PI360-NEW-002: Synthetic fixtures for the new features
- **Description:** Factories and a seed command that create two projects, overlapping youth, employers, placements with changed jobs, feedback and assessments, all synthetic.
- **Existing:** test factories in `backend/tests/`; e2e SQLite seed used by the `pi360-api` launch config.
- **Proposed changes:** Extend the factories. Add a `seed_capyei_demo` management command that refuses to run when `DJANGO_DEBUG` is off.
- **Dependencies:** none (grows with each epic).
- **Priority:** Critical · **Complexity:** Medium · **Estimate:** 1.5 d.
- **Acceptance criteria:** No real names, phones or IDs. Names come from a fixed synthetic list. The command refuses to run in production settings.
- **Tests:** A test checks the command refuses to run without DEBUG. A test checks the seed creates two projects with one youth shared between them.

### PI360-NEW-003: ADR and import-linter contracts
- **Description:** Record the new `apps/assessments` module and the cross-module ids (`EmployerFeedback.placement_id`, `FollowUp.new_placement_id`) in an ADR.
- **Existing:** `planning/04_Technical_Architecture_and_ADRs.md`; `.importlinter` (17 contracts).
- **Proposed changes:** New ADR. Add a contract for `apps.assessments` (may use identity, participants, configuration, audit, platform services).
- **Dependencies:** NEW-001 (D-074 direction).
- **Priority:** High · **Complexity:** Small · **Estimate:** 1 d.
- **Acceptance criteria:** `lint-imports` passes with the new contract. The ADR states the reasons and the alternatives rejected.
- **Tests:** `lint-imports` in CI.

## Epic A: Projects and courses

### PI360-NEW-004: "Project" wording in the UI
- **Description:** Show "Project" wherever users see "Programme" (about 30 frontend files), plus report titles, help guides and spreadsheet headers.
- **Existing:** labels in `frontend/src/pages/**`; `reporting/reports.py` titles; `imports/sample.py` headers; help content files.
- **Proposed changes:** Labels only. No API, DB or scope change (D-070 option a).
- **Dependencies:** D-070.
- **Priority:** High · **Complexity:** Medium · **Estimate:** 3 d.
- **Acceptance criteria:** A grep for user-visible "Programme" returns none outside the code identifiers. API field names are unchanged, so existing clients work.
- **Tests:** Update frontend snapshot and label tests. A Playwright check that the participant list filter says "Project".

### PI360-NEW-005: Optional `project` API alias
- **Description:** Only if D-070 chooses the alias option: accept and return `project`/`project_id` alongside `programme`.
- **Existing:** participant, cohort and report serializers.
- **Proposed changes:** Read-only alias fields; the filter accepts both names.
- **Dependencies:** D-070 (option b). **Blocked.**
- **Priority:** Low · **Complexity:** Medium · **Estimate:** 2 d.
- **Acceptance criteria:** Old and new names return identical results. OpenAPI documents both names and marks `programme` as the canonical one.
- **Tests:** API tests for both parameter names.

### PI360-NEW-006: Course independence migration (with 006a clash report)
- **Description:**
  - **006a:** a read-only management command `course_code_report` that lists course codes used in more than one programme, showing codes and names only.
  - Then migrations to make `Course.programme` nullable and course codes globally unique (data model §3.1).
- **Existing:** `configuration.Course` (required programme FK, unique on `(programme, code)`); `CohortCourse`; `ReferenceAlias`.
- **Proposed changes:** Three-step migration (relax → switch reads → retire, keeping `legacy_programme`).
- **Dependencies:** D-071; the clash report is reviewed by the data steward.
- **Priority:** High · **Complexity:** Large · **Estimate:** 4 d ±1 d (depends on clashes).
- **Acceptance criteria:** Enrollment, cohort-course and placement counts are equal before and after. Every course keeps its programme value in `legacy_programme`. The migration refuses to run while clashes exist.
- **Tests:** Migration tests on a synthetic dataset with a deliberate clash. Reverse migration test.

### PI360-NEW-007: Course and cohort admin UI
- **Description:** Courses are managed as one catalogue. A cohort lists which courses it offers.
- **Existing:** `frontend/src/pages/admin/reference-page.tsx`, `link-courses-dialog.tsx`.
- **Proposed changes:** Remove the programme picker from the course form. Keep and extend the link-courses dialog per cohort.
- **Dependencies:** NEW-006.
- **Priority:** High · **Complexity:** Medium · **Estimate:** 2.5 d.
- **Acceptance criteria:**
  - A course can be linked to cohorts in two projects.
  - Archiving a course that is in use is blocked, with a count of where it is used.
- **Tests:** Component tests for the dialog. API test for linking one course to two cohorts.

### PI360-NEW-008: Import changes for courses and the project header
- **Description:** Course lookup by code alone. Accept `project_code` as a synonym of `programme_code`.
- **Existing:** `imports/sample.py`, the import row parsers, `participants.find_enrollment`.
- **Proposed changes:** Header synonyms. Course lookup by code with `ReferenceAlias` fallback.
- **Dependencies:** NEW-006.
- **Priority:** High · **Complexity:** Medium · **Estimate:** 2 d.
- **Acceptance criteria:** Old template files import unchanged. A new template using `project_code` imports with the same result.
- **Tests:** Import tests for both headers using synthetic files.

### PI360-NEW-009: Go Blue investigation
- **Description:** Find out why the meeting said Go Blue could not be set up. Is it a course code clash, a missing programme or a permission problem? Read-only.
- **Existing:** the configuration data and the import logs on the dev database (counts and codes only).
- **Proposed changes:** A written finding added to D-071. No data change.
- **Dependencies:** none.
- **Priority:** High · **Complexity:** Small · **Estimate:** 1 d ±0.5 d.
- **Acceptance criteria:** The cause is stated with evidence, or "not reproducible" is recorded with the steps tried.
- **Tests:** Not applicable.

## Epic B: Bulk skills verification

### PI360-NEW-010: Bulk verification service
- **Description:** `participants.services.bulk_verify(actor, fact_refs, status, method, notes)` verifies many skills in one go, with all-or-nothing validation.
- **Existing:** `ProfileVerification` (unique per fact), per-entry verify service, audit.
- **Proposed changes:**
  - Reuse `ProfileVerification`; one row per skill, as today.
  - One audit event per skill plus a batch id.
  - Limit of 200 per batch (D-072).
  - Only `verified` and `needs_reassessment` are allowed.
- **Dependencies:** D-072, NEW-011.
- **Priority:** High · **Complexity:** Medium · **Estimate:** 2 d.
- **Acceptance criteria:**
  - Every skill gets `decided_by`, `decided_at`, method and notes.
  - Out-of-scope youth in the batch reject the whole batch with 404-style "not found" ids.
  - Nothing is half-applied.
- **Tests:** Service tests for the scope check, the batch limit and rollback on one invalid item. **Scenario 8.**

### PI360-NEW-011: `participants.verify` permission
- **Description:** Separate "can verify" from "can edit" (D-072).
- **Existing:** permission catalogue in `identity`; `participants.edit` currently covers verification.
- **Proposed changes:** New catalogue entry. A data migration grants it to roles that hold `participants.edit` today, so behaviour is unchanged.
- **Dependencies:** D-072.
- **Priority:** High · **Complexity:** Small · **Estimate:** 1 d.
- **Acceptance criteria:** Existing roles keep the ability to verify. An administrator can remove it from a role.
- **Tests:** Authz matrix rows. Data-migration test.

### PI360-NEW-012: Bulk verification endpoint
- **Description:** `POST /api/participants/verifications/bulk/`.
- **Existing:** DRF views with `required_permission`.
- **Proposed changes:** New view and serializer (unique name); response contains a per-item result.
- **Dependencies:** NEW-010, NEW-011.
- **Priority:** High · **Complexity:** Small · **Estimate:** 1.5 d.
- **Acceptance criteria:** 403 without `participants.verify`; 404 for out-of-scope ids; 400 over the limit.
- **Tests:** API tests; authz matrix.

### PI360-NEW-013: Verification queue page with bulk bar
- **Description:** A list of pending skills with filters (project, cohort, course, skill) and select-all-on-page plus a BulkBar.
- **Existing:** `skills-dialog.tsx`; the participant directory table and its existing bulk-action pattern.
- **Proposed changes:** New page reusing the existing data-table and BulkBar components. A confirm dialog shows the count and the method.
- **Dependencies:** NEW-012.
- **Priority:** High · **Complexity:** Medium · **Estimate:** 3 d.
- **Acceptance criteria:**
  - Keyboard-operable.
  - The confirm dialog states the number of skills.
  - The success toast links to the audit view.
  - It works on a 375 px screen.
- **Tests:** Component tests; a Playwright run verifying 3 synthetic skills; an axe check.

## Epic C: Open for Opportunities

### PI360-NEW-014: Availability fields and history
- **Description:** Add `open_to_opportunities` and its metadata to `ParticipantReadiness`, plus an append-only `AvailabilityChange` model (data model §3.2).
- **Existing:** `ParticipantReadiness`.
- **Proposed changes:** Additive migration and a `set_availability` service.
- **Dependencies:** D-073.
- **Priority:** High · **Complexity:** Medium · **Estimate:** 2 d.
- **Acceptance criteria:** Every change writes one history row with source, actor and reason. History rows cannot be edited.
- **Tests:** Model test that save on an existing row raises. Service tests.

### PI360-NEW-015: Derived employment situation
- **Description:** A service that returns never_placed / placed / self_employed / exited from the Placement episodes.
- **Existing:** `placements.services` episodes.
- **Proposed changes:** `placements.services.situation_for(participant_ids)`, batched for lists.
- **Dependencies:** none.
- **Priority:** High · **Complexity:** Small · **Estimate:** 1.5 d.
- **Acceptance criteria:** A concurrent second job counts as placed. An ended-only history counts as exited.
- **Tests:** Table-driven unit tests.

### PI360-NEW-016: Matching pool policy
- **Description:** `suggest_youth` excludes youth who are not open, using the D-073 defaults.
- **Existing:** `intelligence.suggest_youth`, `capability_snapshots`.
- **Proposed changes:** Filter by effective availability (explicit value, else the default by situation). Add setting `matching.include_placed_default` (default false).
- **Dependencies:** NEW-014, NEW-015, D-073.
- **Priority:** Critical · **Complexity:** Medium · **Estimate:** 2 d.
- **Acceptance criteria:** A placed youth with availability off never appears. A placed youth who opted in does appear, labelled "currently employed".
- **Tests:** **Scenario 4.** Regression of the existing matching tests.

### PI360-NEW-017: Staff and portal availability toggle
- **Description:** A toggle on the profile page and in the youth portal.
- **Existing:** `profile-page.tsx`; `portal/my-details`.
- **Proposed changes:** The toggle shows the current situation and "last changed by/when". Staff must give a reason when overriding.
- **Dependencies:** NEW-014.
- **Priority:** High · **Complexity:** Medium · **Estimate:** 2 d.
- **Acceptance criteria:** The youth sees their own value only. Staff need `participants.edit`.
- **Tests:** Component tests; portal authz test.

### PI360-NEW-018: Referral warning
- **Description:** Warn, without blocking, when referring a youth who is not open.
- **Existing:** the referral create dialog.
- **Proposed changes:** The warning text plus an "I have checked with the youth" confirmation, which is audited.
- **Dependencies:** NEW-016.
- **Priority:** Medium · **Complexity:** Small · **Estimate:** 1 d.
- **Acceptance criteria:** The warning shows and the referral can still proceed. Existing referrals are never withdrawn.
- **Tests:** Component test; service test.

## Epic D1: Trainer competency assessment

### PI360-NEW-019: Assessment models
- **Description:** Template, Version, Scale, Category, Criterion, Assessment and Score in the new `apps/assessments` (data model §3.3).
- **Existing:** none (YDM spec in `planning/16_YDM_Assessment_Specification.md`; `ydm.*` permissions).
- **Proposed changes:** New app, models and additive migration.
- **Dependencies:** NEW-003, D-074.
- **Priority:** High · **Complexity:** Large · **Estimate:** 4 d.
- **Acceptance criteria:**
  - An approved version cannot be edited.
  - A submitted assessment cannot be edited.
  - A correction creates a superseding row.
- **Tests:** Model immutability tests; migration test.

### PI360-NEW-020: Scoring service
- **Description:** Compute category scores, total and completion according to the version's method and missing-score policy.
- **Existing:** none.
- **Proposed changes:** A pure function plus the stored `computed` JSON, which records the method version.
- **Dependencies:** NEW-019, D-074 (method).
- **Priority:** High · **Complexity:** Medium · **Estimate:** 2.5 d.
- **Acceptance criteria:**
  - Equal and weighted methods give documented results.
  - Missing scores follow the policy.
  - Below the minimum completion, no total is shown.
- **Tests:** Table-driven unit tests with synthetic score sets.

### PI360-NEW-021: Template administration
- **Description:** Administrators create templates, versions, categories, criteria and scales, then approve them.
- **Existing:** rules lifecycle UI pattern (draft → approved).
- **Proposed changes:** New admin pages reusing the existing form and table components.
- **Dependencies:** NEW-019.
- **Priority:** Medium · **Complexity:** Medium · **Estimate:** 3 d.
- **Acceptance criteria:** Only an Administrator approves. An approved version is read-only in the UI.
- **Tests:** Component and API tests.

### PI360-NEW-022: Capture UI (per youth and cohort grid)
- **Description:** A trainer scores one youth, or a cohort in a grid.
- **Existing:** the cohort and participant pages.
- **Proposed changes:** A per-youth form and a cohort grid with save as draft and submit.
- **Dependencies:** NEW-020, NEW-024, D-075.
- **Priority:** High · **Complexity:** Large · **Estimate:** 4 d ±1 d.
- **Acceptance criteria:**
  - Draft autosave.
  - Submit locks the assessment.
  - The grid is keyboard-navigable.
  - Out-of-scope youth are not listed.
- **Tests:** Component tests; Playwright cohort grid; axe check.

### PI360-NEW-023: Assessment history on the profile
- **Description:** Show assessments over time, including the superseded chain.
- **Existing:** `profile-page.tsx` tabs.
- **Proposed changes:** A new tab with a version-aware comparison.
- **Dependencies:** NEW-022.
- **Priority:** Medium · **Complexity:** Medium · **Estimate:** 2 d.
- **Acceptance criteria:** Superseded rows are marked. Comparison only happens across the same template version.
- **Tests:** Component tests.

### PI360-NEW-024: Assessor permissions and role
- **Description:** Activate the Assessor role (inactive "until D-024") with `assessments.view/capture`.
- **Existing:** `identity/defaults.py` Assessor role.
- **Proposed changes:** Catalogue entries; the role is activated by data migration only after the decision.
- **Dependencies:** D-024, D-075.
- **Priority:** High · **Complexity:** Small · **Estimate:** 1 d.
- **Acceptance criteria:** An assessor sees only assigned cohorts. A youth never sees trainer comments.
- **Tests:** Authz matrix; **Scenario 7.**

### PI360-NEW-025: IYLDP import
- **Description:** Optionally import past IYLDP spreadsheets.
- **Existing:** the import framework (dry run then commit).
- **Proposed changes:** A new import type mapping columns to criteria.
- **Dependencies:** NEW-019, D-058. **Blocked.**
- **Priority:** Low · **Complexity:** Medium · **Estimate:** 3 d ±1 d.
- **Acceptance criteria:** The dry run shows unmatched youth and criteria. Nothing is written before commit.
- **Tests:** Import tests with a synthetic sheet.

## Epic D2: Employer ratings

### PI360-NEW-026: Extend EmployerFeedback with criteria
- **Description:** Add `placement_id`, kind, channel and review_status, plus `FeedbackCriterion` and `EmployerFeedbackScore` (data model §3.4).
- **Existing:** `EmployerFeedback` (single rating), `employers.add_feedback`.
- **Proposed changes:** Additive migration. `add_feedback` accepts criterion scores.
- **Dependencies:** D-077, NEW-003.
- **Priority:** High · **Complexity:** Medium · **Estimate:** 3 d.
- **Acceptance criteria:** Existing rows and indicators are unchanged. A criterion score outside 1–5 is rejected.
- **Tests:** Migration test; service tests.

### PI360-NEW-027: Employer feedback summary
- **Description:** Per-criterion averages and counts, hidden below `employer.min_feedback`.
- **Existing:** `intelligence.employer_evidence`, `employers.feedback_counts`.
- **Proposed changes:** Extend `employer_evidence` with a criteria block. It returns "insufficient" below the threshold.
- **Dependencies:** NEW-026.
- **Priority:** High · **Complexity:** Medium · **Estimate:** 2 d.
- **Acceptance criteria:** Below the threshold there is no average and no overall rating (D-027). Excluded rows are not counted.
- **Tests:** **Scenario 6.**

### PI360-NEW-028: Alerts and review queue
- **Description:** Open an `EmployerReview` when the settings thresholds are crossed. Administrators record the outcome.
- **Existing:** the settings registry; the dashboard alerts pattern.
- **Proposed changes:**
  - New model and a nightly check, using the existing job pattern.
  - A queue page.
  - No automatic suspension.
- **Dependencies:** NEW-027, D-078.
- **Priority:** Medium · **Complexity:** Medium · **Estimate:** 3 d.
- **Acceptance criteria:**
  - With the settings empty, no alerts fire.
  - Each outcome needs a reason.
  - History is kept.
- **Tests:** Service tests with the threshold set and unset.

### PI360-NEW-029: Employer rating UI
- **Description:** Criterion form for staff and the summary on the employer page.
- **Existing:** `employer-feedback.tsx`, `employer-evidence.tsx`.
- **Proposed changes:** Extend both. Comments are visible only with the right permission.
- **Dependencies:** NEW-027.
- **Priority:** High · **Complexity:** Medium · **Estimate:** 2.5 d.
- **Acceptance criteria:** The employer portal never shows these. "Insufficient evidence" wording matches D-027.
- **Tests:** Component tests; employer-portal authz test.

## Epic E: Matching

### PI360-NEW-030: B-COMP factor
- **Description:** A preferred factor on competency results in `pi360_rules`.
- **Existing:** `pi360_rules` factors B-QUAL to B-COND; the rule lifecycle.
- **Proposed changes:** New factor. Unknown is never a fail. Weight `w_comp`.
- **Dependencies:** NEW-020, D-076, D-052–D-058. **Blocked.**
- **Priority:** Medium · **Complexity:** Medium · **Estimate:** 3 d.
- **Acceptance criteria:** A mandatory mismatch stays not_eligible whatever the competency score.
- **Tests:** **Scenario 3.** Rules regression suite.

### PI360-NEW-031: Competency in the capability snapshot
- **Description:** Add the latest submitted assessment summary to `capability_snapshots`.
- **Existing:** `intelligence.capability_snapshots`.
- **Proposed changes:** A read through `assessments.services`.
- **Dependencies:** NEW-020.
- **Priority:** Medium · **Complexity:** Small · **Estimate:** 1 d.
- **Acceptance criteria:** Superseded and draft assessments are ignored.
- **Tests:** Unit tests.

### PI360-NEW-032: Draft rule version and regression
- **Description:** Create a draft rule version that uses B-COMP and compare its results with the active one.
- **Existing:** rule versions; the regression fixtures.
- **Proposed changes:** Draft version plus a comparison report. Approval stays with the Administrator (D-009).
- **Dependencies:** NEW-030, NEW-031.
- **Priority:** Medium · **Complexity:** Medium · **Estimate:** 2 d.
- **Acceptance criteria:** The report lists every eligibility change. No eligibility changes caused by preferred factors.
- **Tests:** Regression suite.

### PI360-NEW-033: Employer ranking column
- **Description:** Show employer feedback evidence beside matches as a separate column, not a composite score (D-087).
- **Existing:** the opportunity match list.
- **Proposed changes:** A column with "insufficient" handling.
- **Dependencies:** NEW-027, D-087.
- **Priority:** Low · **Complexity:** Medium · **Estimate:** 3 d.
- **Acceptance criteria:** The youth's eligibility and order do not change because of this column.
- **Tests:** Component tests.

## Epic F: Follow-up and employment history

### PI360-NEW-034: Follow-up outcome fields
- **Description:** outcome, leaving_reason, observations and new_placement_id on `FollowUp`, plus the `LeavingReason` reference list.
- **Existing:** `FollowUp.still_employed`, `FollowUpAttempt`.
- **Proposed changes:** Additive migration. `still_employed` is derived from outcome.
- **Dependencies:** D-080.
- **Priority:** High · **Complexity:** Medium · **Estimate:** 2 d.
- **Acceptance criteria:** Old rows read as "not recorded". Retention counts are unchanged.
- **Tests:** Migration test; retention regression.

### PI360-NEW-035: Placement employment type and remuneration
- **Description:** `employment_type` and `previous_placement` now; `remuneration_band` only after D-080/D-090.
- **Existing:** `Placement` with `REVIEWABLE`.
- **Proposed changes:** Additive fields and reference lists.
- **Dependencies:** D-080, D-090 (band).
- **Priority:** Medium · **Complexity:** Small · **Estimate:** 1.5 d.
- **Acceptance criteria:** The band is visible only with the restricted permission.
- **Tests:** Model tests; authz.

### PI360-NEW-036: `record_outcome` service
- **Description:** One transaction that records the follow-up outcome and ends and/or creates episodes (data model §3.5).
- **Existing:** `record_manual`, `end_episode`, `running_with_employer`.
- **Proposed changes:** A new service in `placements.followups`.
- **Dependencies:** NEW-034, NEW-035, D-081.
- **Priority:** Critical · **Complexity:** Large · **Estimate:** 3 d.
- **Acceptance criteria:**
  - The original episode is never overwritten.
  - The new episode links `previous_placement` and gets its own follow-up schedule.
  - Duplicates are warned about.
- **Tests:** **Scenario 5.** Rollback test.

### PI360-NEW-037: Retention calculations
- **Description:** "With the same employer" and "in any work" at each milestone (D-080).
- **Existing:** `retention_counts`, `reports.retention`.
- **Proposed changes:** Two measures that use the episode chain.
- **Dependencies:** NEW-036, D-089.
- **Priority:** High · **Complexity:** Medium · **Estimate:** 2 d.
- **Acceptance criteria:** A job change counts in "any work" but not in "same employer". Both definitions are shown on screen.
- **Tests:** Table-driven tests on synthetic chains.

### PI360-NEW-038: Follow-up UI
- **Description:** Outcome form with conditional fields for a new employer or a reason for leaving.
- **Existing:** `followup-page.tsx`, `followup-table.tsx`, `followup-shared.tsx`.
- **Proposed changes:** Extend the existing form and table.
- **Dependencies:** NEW-036.
- **Priority:** High · **Complexity:** Medium · **Estimate:** 3 d.
- **Acceptance criteria:**
  - Choosing "changed employer" asks for the new employer and start date.
  - The confirmation explains that a new episode will be created.
  - Works on mobile.
- **Tests:** Component tests; Playwright run.

## Epic G: Exit feedback

### PI360-NEW-039: Exit feedback form (staff-assisted)
- **Description:** When an episode ends, capture the reason (on Placement) and the rating and comments (on EmployerFeedback, kind=exit).
- **Existing:** `end_episode`; `EmployerFeedback`.
- **Proposed changes:** Service plus staff form; one exit feedback per episode.
- **Dependencies:** NEW-026, NEW-036, D-079.
- **Priority:** Medium · **Complexity:** Medium · **Estimate:** 2.5 d.
- **Acceptance criteria:** A second exit feedback for the same episode is rejected. Never shown individually to the employer.
- **Tests:** Service tests; employer-portal authz.

## Epic H: Disability

### PI360-NEW-040: Disability fields
- **Description:** `disability`, `disability_recorded_at`, `disability_source` on Participant, behind a flag.
- **Existing:** none (Participant has no field).
- **Proposed changes:** Additive migration (default not_recorded); permission `participants.view_disability`.
- **Dependencies:** D-082, D-063, D-090. **Blocked for enablement**; the migration can be prepared.
- **Priority:** High · **Complexity:** Medium · **Estimate:** 2.5 d.
- **Acceptance criteria:** With the flag off, the API returns 404 or omits the field. Without the permission, the field is omitted.
- **Tests:** Authz matrix; serializer tests.

### PI360-NEW-041: Disability in forms
- **Description:** Field after Gender in add-youth and participant-edit.
- **Existing:** `add-youth.tsx` (Gender at about line 400), `participant-edit.tsx`.
- **Proposed changes:** A select with the four options and help text that says why it is asked.
- **Dependencies:** NEW-040.
- **Priority:** High · **Complexity:** Small · **Estimate:** 1.5 d.
- **Acceptance criteria:** Optional; "Prefer not to say" is respected. "Jeddah" placement is confirmed with CAP-YEI (D-082).
- **Tests:** Component tests; axe check.

### PI360-NEW-042: Import mapping (dry run)
- **Description:** Report which imported `extra` keys might hold disability data, then map them only after approval.
- **Existing:** `ParticipantEnrollment.extra`.
- **Proposed changes:** A key-name report (no values) plus an opt-in mapping that writes `disability_source=import`.
- **Dependencies:** NEW-040, D-082.
- **Priority:** Low · **Complexity:** Medium · **Estimate:** 2 d.
- **Acceptance criteria:** No value is copied without an approved mapping. The report shows counts only.
- **Tests:** Import tests with synthetic `extra`.

### PI360-NEW-043: Disability in reports
- **Description:** Disaggregate `equity_and_reach` and the scorecards with small-cell suppression.
- **Existing:** `reports.equity_and_reach` (line 823 says it is not collected); `NOT_CAPTURED`.
- **Proposed changes:** Remove it from NOT_CAPTURED when enabled; apply suppression.
- **Dependencies:** NEW-040, D-089.
- **Priority:** Medium · **Complexity:** Small · **Estimate:** 1.5 d.
- **Acceptance criteria:** Cells below `exports.small_cell` are suppressed. "Not recorded" is shown as its own group.
- **Tests:** Report tests.

## Epic I: Self-registration

### PI360-NEW-044: RegistrationRequest model
- **Description:** Data model §3.7.
- **Existing:** `YouthInvite` token-hash pattern.
- **Proposed changes:** New model in `portal`; additive migration.
- **Dependencies:** D-083, D-090.
- **Priority:** Medium · **Complexity:** Medium · **Estimate:** 3 d.
- **Acceptance criteria:** Only hashes of tokens and OTPs are stored; no raw IP.
- **Tests:** Model tests.

### PI360-NEW-045: Public registration endpoints
- **Description:** Submit, verify email/phone, and status.
- **Existing:** activation endpoints; throttling settings.
- **Proposed changes:** Unauthenticated endpoints with rate limits and generic responses.
- **Dependencies:** NEW-044, NEW-048.
- **Priority:** Medium · **Complexity:** Large · **Estimate:** 3 d.
- **Acceptance criteria:**
  - The response never reveals whether a person exists.
  - Rate-limited per IP hash and per contact.
  - 404 when the flag is off.
- **Tests:** API tests incl. enumeration; throttle tests.

### PI360-NEW-046: Officer review queue
- **Description:** Officers match, link, create or reject requests.
- **Existing:** `similar.similar_to`, `duplicates.find_pairs`, `create_participant`.
- **Proposed changes:** Queue page plus a service that shows similar participants (in scope only) and requires a decision reason.
- **Dependencies:** NEW-044.
- **Priority:** Medium · **Complexity:** Large · **Estimate:** 4 d ±1 d.
- **Acceptance criteria:** Linking never creates a new participant. A "create" decision warns when a similar person exists.
- **Tests:** **Scenario 9.** Service tests.

### PI360-NEW-047: Activation reuse
- **Description:** Approval sends the existing invite.
- **Existing:** `portal.services.send_invite`/`activate`.
- **Proposed changes:** Call them; no second account path.
- **Dependencies:** NEW-046.
- **Priority:** Medium · **Complexity:** Small · **Estimate:** 1.5 d.
- **Acceptance criteria:** One youth account per participant.
- **Tests:** Service test.

### PI360-NEW-048: Self-registration feature flag
- **Description:** Flag `portal.self_registration`, off by default.
- **Existing:** feature flag mechanism (404 when off).
- **Proposed changes:** New flag.
- **Dependencies:** none.
- **Priority:** Medium · **Complexity:** Small · **Estimate:** 0.5 d.
- **Acceptance criteria:** Off returns 404 and hides the link.
- **Tests:** Flag test.

### PI360-NEW-049: Self-registration frontend
- **Description:** Public form, verification steps and status page.
- **Existing:** `activate-page.tsx`.
- **Proposed changes:** New pages with the same layout, a privacy notice (version from D-090) and a mobile-first design.
- **Dependencies:** NEW-045.
- **Priority:** Medium · **Complexity:** Large · **Estimate:** 4 d.
- **Acceptance criteria:** WCAG 2.1 AA; usable at 375 px; generic messages.
- **Tests:** Playwright; axe.

## Epic J: Review status

### PI360-NEW-050: Review state and triggers
- **Description:** `review_state` fields; triggers on self-registration, self-edit, import change and officer flag; a bulk "mark reviewed".
- **Existing:** `Participant.status`.
- **Proposed changes:** Additive fields plus a service. Never blocks other actions (D-084).
- **Dependencies:** D-084.
- **Priority:** Medium · **Complexity:** Medium · **Estimate:** 2.5 d.
- **Acceptance criteria:** Existing youth start at none. Each trigger sets a reason code.
- **Tests:** Service tests.

### PI360-NEW-051: Review UI
- **Description:** A filter and badge in the directory; a bulk mark-reviewed action.
- **Existing:** `directory-page.tsx`, BulkBar.
- **Proposed changes:** Extend.
- **Dependencies:** NEW-050.
- **Priority:** Medium · **Complexity:** Medium · **Estimate:** 2 d.
- **Acceptance criteria:** The badge has a text label, not only colour.
- **Tests:** Component tests.

## Epic K: Youth portal

### PI360-NEW-052: Placement history and job-change self-report
- **Description:** The youth sees their episodes and can report "I changed jobs". The report goes to the officer as a follow-up task.
- **Existing:** `my-placement.tsx`.
- **Proposed changes:** List of episodes; a self-report form that creates a review flag and does not change placements directly.
- **Dependencies:** NEW-036, NEW-050.
- **Priority:** Medium · **Complexity:** Medium · **Estimate:** 3 d.
- **Acceptance criteria:** A youth sees only their own data; their report never overwrites an episode.
- **Tests:** Portal authz; **Scenario 7.**

### PI360-NEW-053: Portal exit form
- **Description:** The youth gives exit feedback themselves.
- **Existing:** portal pages.
- **Proposed changes:** A form that writes `channel=portal`.
- **Dependencies:** NEW-039, D-079.
- **Priority:** Low · **Complexity:** Medium · **Estimate:** 2 d.
- **Acceptance criteria:** One per episode; the youth can see but not edit after submitting.
- **Tests:** Portal tests.

### PI360-NEW-054: Portal opportunity suggestions
- **Description:** Suggested opportunities in `my-opportunities`.
- **Existing:** `my-opportunities.tsx` (referral-only today).
- **Proposed changes:** Show matches for the youth, if D-006/D-007 allow it.
- **Dependencies:** D-088, D-006, D-007. **Blocked.**
- **Priority:** Low · **Complexity:** Medium · **Estimate:** 3 d.
- **Acceptance criteria:** Respects availability; no scores are shown.
- **Tests:** Portal tests.

### PI360-NEW-055: Portal mobile and accessibility pass
- **Description:** Check all new portal screens at 375 px and with axe.
- **Existing:** portal pages.
- **Proposed changes:** Fixes only.
- **Dependencies:** NEW-052, NEW-053, NEW-049.
- **Priority:** Medium · **Complexity:** Small · **Estimate:** 1.5 d.
- **Acceptance criteria:** No serious axe violations.
- **Tests:** axe in Playwright.

## Epic L: Project isolation

### PI360-NEW-056: Project officer role
- **Description:** A default role "Project officer" (assigned scope, placement-officer permissions), created by a data migration.
- **Existing:** `identity/defaults.py` Placement officer.
- **Proposed changes:** New role row, created only if absent.
- **Dependencies:** D-085.
- **Priority:** Critical · **Complexity:** Small · **Estimate:** 1.5 d.
- **Acceptance criteria:** Existing role rows are untouched. No assignment means no access.
- **Tests:** Data migration test.

### PI360-NEW-057: Scope assignment UI for projects
- **Description:** Assign one or more projects to a user.
- **Existing:** `users-page.tsx`, `access-grants.tsx`.
- **Proposed changes:** Reword "programme" to "project" in the scope picker.
- **Dependencies:** NEW-004.
- **Priority:** Critical · **Complexity:** Small · **Estimate:** 1 d.
- **Acceptance criteria:** Shows the current assignments clearly.
- **Tests:** Component test.

### PI360-NEW-058: Opportunity project scoping
- **Description:** Only if D-086 is option (b): `Opportunity.projects`.
- **Existing:** `Opportunity` (global).
- **Proposed changes:** M2M plus a scope helper.
- **Dependencies:** D-086. **Blocked.**
- **Priority:** Low · **Complexity:** Large · **Estimate:** 4 d.
- **Acceptance criteria:** An empty list means shared.
- **Tests:** Scope tests.

### PI360-NEW-059: Orphan youth policy and report
- **Description:** Youth with no enrollment are seen only by all-scope roles. A report lists them for the data steward.
- **Existing:** `Participant.scope_map`.
- **Proposed changes:** Report (counts and ids) plus a help guide note.
- **Dependencies:** D-085.
- **Priority:** High · **Complexity:** Small · **Estimate:** 1 d.
- **Acceptance criteria:** A project officer never sees orphans.
- **Tests:** Scope test.

### PI360-NEW-060: Import and export scope
- **Description:** Imports and exports respect project scope.
- **Existing:** `imports.run/commit`, `participants.export_groups`.
- **Proposed changes:** Reject import rows for projects outside the importer's scope; filter exports by `visible_ids`.
- **Dependencies:** NEW-056.
- **Priority:** Critical · **Complexity:** Medium · **Estimate:** 2 d.
- **Acceptance criteria:** An export contains only authorized records. An import into another project is rejected per row.
- **Tests:** **Scenario 10.**

### PI360-NEW-061: Authorization test suite
- **Description:** Cross-project tests over every participant-linked endpoint, plus the employer-portal confidentiality checks.
- **Existing:** `tests/test_authz_matrix.py`.
- **Proposed changes:** A parametrised suite with two projects and one shared youth.
- **Dependencies:** NEW-002, NEW-056.
- **Priority:** Critical · **Complexity:** Medium · **Estimate:** 3 d.
- **Acceptance criteria:** Every out-of-scope request returns 404. A shared youth is visible to both officers.
- **Tests:** **Scenarios 1, 2, 7 and 10.**

## Epic M: Reporting

### PI360-NEW-062: Metric definitions
- **Description:** Add the new metrics to `reporting/services.py METRICS` with meaning and approval flag.
- **Existing:** `METRICS`, `NOT_CAPTURED`.
- **Proposed changes:** Entries with `approved=False` until D-089.
- **Dependencies:** D-089.
- **Priority:** High · **Complexity:** Small · **Estimate:** 1 d.
- **Acceptance criteria:** Unapproved metrics are labelled as such on screen.
- **Tests:** Unit test.

### PI360-NEW-063: Dashboard tiles
- **Description:** Project-filtered tiles: placed, open for opportunities, follow-ups due, conversion.
- **Existing:** dashboard page.
- **Proposed changes:** New tiles using existing components.
- **Dependencies:** NEW-062, NEW-016, NEW-037.
- **Priority:** Medium · **Complexity:** Medium · **Estimate:** 3 d.
- **Acceptance criteria:** Respects scope; each tile shows its definition.
- **Tests:** Component tests; scope test.

### PI360-NEW-064: Reports
- **Description:** Project scorecard; retention at 30/90 days and 6/12/24 months; changed employer; self-employment; referral conversion; employer responsiveness.
- **Existing:** `reports.py` (programme_scorecard, retention, employer_pipeline).
- **Proposed changes:** Extend those functions; do not add a new reporting layer.
- **Dependencies:** NEW-037, NEW-062.
- **Priority:** High · **Complexity:** Large · **Estimate:** 4 d.
- **Acceptance criteria:** Each figure links to its definition; small cells are suppressed.
- **Tests:** Report tests with synthetic data.

## Cross-cutting close

### PI360-NEW-065: Help guides
- **Description:** Update staff, officer, youth and employer guides for all the features above.
- **Existing:** `frontend/src/pages/help/content-*.ts`, `guides.ts`.
- **Proposed changes:** New and updated guides.
- **Dependencies:** each feature.
- **Priority:** High · **Complexity:** Medium · **Estimate:** 3 d.
- **Acceptance criteria:** Every new screen has a guide entry.
- **Tests:** The existing help-content test.

### PI360-NEW-066: OpenAPI, authz matrix and CI
- **Description:** Final check that all routes are in the matrix and the OpenAPI is current.
- **Existing:** CI pipeline.
- **Proposed changes:** None beyond the checks.
- **Dependencies:** all API tasks.
- **Priority:** Critical · **Complexity:** Small · **Estimate:** 1 d.
- **Acceptance criteria:** CI green.
- **Tests:** CI.

### PI360-NEW-067: Playwright end-to-end for the 10 scenarios
- **Description:** One e2e test per scenario on the synthetic seed.
- **Existing:** Playwright setup.
- **Proposed changes:** New specs.
- **Dependencies:** NEW-002 and the related features.
- **Priority:** Critical · **Complexity:** Large · **Estimate:** 4 d.
- **Acceptance criteria:** All 10 pass in CI.
- **Tests:** Itself.

### PI360-NEW-068: UAT and release notes
- **Description:** UAT script for CAP-YEI and release notes.
- **Existing:** previous release notes.
- **Proposed changes:** Documents only.
- **Dependencies:** all tasks in the release.
- **Priority:** High · **Complexity:** Medium · **Estimate:** 2 d.
- **Acceptance criteria:** CAP-YEI signs off each scenario.
- **Tests:** UAT.
