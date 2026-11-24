# CAP-YEI answers of 23 November 2026: impact assessment and revised plan

**PI360** · Planning document · 23 Nov 2026 · Status: **for review before any code changes**.

**Source:** "Consolidated Decision Register: Questions and Answers". CAP-YEI and the DPO answered the decision pack (`docs/capyei-decision-pack.md`), and the user passed their answers to the PI360 team on 23 Nov 2026.

**Rules this document follows:**
- An answer is a requirement only where the source says it is confirmed.
- Suggestions from the decision pack that the source did not confirm stay suggestions. They are listed in §6.
- Pending items are flagged, not guessed.

**Code evidence:**
- Read-only searches of `pi360/backend` and `pi360/frontend`.
- Row counts on the dev database, which holds synthetic and e2e data only. No personal values were read.

Companion documents, updated to match:
- `capyei-decision-register.md` (decision statuses);
- `capyei-meeting-implementation-plan.md` (phases);
- `capyei-implementation-backlog.md` (task changes);
- `capyei-metric-definitions.md` (new; for B43);
- `planning/registers/decisions.csv`.

---

## 1. Decision status after the answers

| Decision | Pack items | Status now | What is still open |
|---|---|---|---|
| D-070 Project wording | B1 | **Decided:** rename everywhere, including the database and API | — |
| D-071 Courses and Go Blue | B2–B5 | **Decided:** a shared course catalogue; keep the cohort label plus structured fields; keep courses 001–007, including SIYB | The project-setup sheet arrives when the import task starts (B3). |
| D-072 Bulk verification | B6–B8 | **Decided** | Reason for individual rejection: recommended, not confirmed. |
| D-073 Open for Opportunities | B9–B12 | **Decided** | **C-1:** the default for youth who are placed now or were placed before. |
| D-074 Instrument | B13 | **Decided:** one instrument, 6 competencies, 26 criteria | — |
| D-075 Who assesses | B16, B17 | **Decided:** Administrators and Placement officers; the first assessment is at the end of training | An approval step (B16) and a reassessment interval (B17). |
| D-076 Assessments in matching | B18 | **Decided:** assessments are a weighted factor | The weight. |
| D-077 Employer ratings | B19, B20, A6 | **Open** | The five criteria (B19); the minimum count before employers see aggregates (A6). The scale is decided: 1 Very Poor to 5 Excellent. |
| D-078 Employer alerts | B21–B23 | **Decided** | — |
| D-079 Exit feedback | A4 | **Decided** | — |
| D-080 Follow-up data | A3, B25–B27 | **Decided** | — |
| D-081 Concurrent placements | B28 | **Decided:** no; one active placement | **C-3:** what an import does when it would create a second active placement. |
| D-082 Disability | A1, B30–B32 | **Decided** | Field position "after Gender" to confirm when the form is finalised (B30). |
| D-083 Self-registration | A5, B33, B34 | **Decided** | Consent wording is a draft that needs CAP-YEI approval. |
| D-084 Needs Review | B35, B36 | **Decided** | — |
| D-085 Project Officer | B37–B40 | **Decided** | **C-2:** how identifiable export fits PI360's grant-only design (§3.3). |
| D-086 Shared employers | B41 | **Decided** | — |
| D-087 Employer quality in ranking | B24 | **Decided** | **C-4:** PI360 has no "suspended" employer status. The size of the penalty is open. |
| D-088 Portal opportunities | B42 | **Decided:** referred only | — |
| D-089 Metrics | B43 | **Open** | Plan "§5.13" does not exist; that was a broken reference in our pack. Definitions are now in `capyei-metric-definitions.md`. |
| D-090 Privacy | A2 | **Open** | CAP-YEI said it may keep the data as long as it wants. The DPO must still confirm the lawful basis, notices and retention. |

Older decisions these answers touch:
- **Decided:**
  - D-052: scale 1–5 with meanings, from B15.
  - D-054: equal weights by plain average, from B15.
  - D-065: YDM/IYLDP is in pilot scope, from B14.
- **Partly answered, still Open:**
  - D-053: point meanings answered; no thresholds or bands given.
  - D-055: blanks are excluded and the completed count is shown; no completeness minimum given.
  - D-056: who records answered; approval and template management not.
  - D-057: one instrument answered; the "2nd" plan not.
  - D-062: course 006 is kept; other unclear fields not answered.
  - D-063: disability and salary answered; other sensitive fields not.
  - D-066: CAP-YEI said "keep full history" but did not say whether the Go Blue sheet *is* the full history.

## 2. Mapping to the code

| Decision | Affected code (evidence) | Change |
|---|---|---|
| B1 rename | 305 mentions in 26 backend modules (excluding migrations); 168 in the frontend; 16 test files; scope kind `"programme"` stored in `ScopeAssignment` rows and `Participant.scope_map`; import template columns; `ParticipantEnrollment.programme` | Rename models, fields, tables, API fields, scope kind, permissions text, import headers and UI. §3.1 |
| B2 courses | `Course.programme` FK required; unique `(programme, code)` | Make the course global with a unique code. Project offerings come through `CohortCourse` (cohort → project). |
| B4 cohort | `Cohort` already has `intake_year`, `batch_no`, `phase`, `year_of_study` and `institution`; `name` "holds the label" (models.py:118) | **Mostly met already.** Check that imports keep the full original label in `name`. Possibly add `source_label` if `name` is edited. |
| B5 courses | none | A seed or reference-data step for courses 001–007 (codes and names only). |
| B6–B8 bulk verify | `ProfileVerification` per fact | Bulk service and UI. The allowed roles are Administrator, Placement officer and Project officer. |
| B9–B12 availability | `ParticipantReadiness`; `suggest_youth` | An independent flag and its history; matching excludes Closed youth; a warning on existing referrals. |
| B13–B18 assessments | `ydm.view/assess/manage` permissions exist; Assessor role inactive; no model | New `assessments` module. Give `ydm.assess` to Administrator and Placement officer only, **not** Project officer. B-COMP factor with its weight unset. |
| B20–B23 employer ratings | `EmployerFeedback` holds a single rating | Scale labels; negative is 1–2; alert when there are ≥3 ratings averaging <3.0, or any single rating of 1; review outcomes Monitor / Ignore. |
| A6 employer aggregates | Employer portal never reads `EmployerFeedback` | A new employer-portal view, **off until the minimum count is decided**. |
| A4 exit feedback | `Placement.exit_reason` | A feedback record that stores **its own `confidential` value**, plus an admin setting (default ON). |
| A3, B25–B27 follow-ups | `FollowUp.still_employed` only | Outcome, employment type (8 values), leaving reason (8), exact salary **and** band, self-employment details (7 fields). |
| B26 retention metric | Follow-up steps at 30 d, 90 d, 6, 12 and 24 months | Report 3, 6 and 12 months, split by "same employer" and "another employer". The 90 d step stands for 3 months. |
| B28 one active placement | `record_manual` does not check for a running placement; `running_with_employer` only warns (placements/services.py:208) | **Behaviour change.** §3.2 |
| A1, B31, B32 disability | None; `reports.py` says it is not collected | One record per youth (Yes/No plus an optional description). The permission is checked in the backend. Every read and change is audited. Historical Go Blue import maps blank to "not recorded". |
| A5, B33, B34 self-registration | Invite-only `YouthInvite` | Direct sign-up with **no officer approval**. Verification is supported and switched off for the pilot. A duplicate check at sign-up; the account goes to the Self-Registration Queue. Rejected requests are kept until an admin deletes them. |
| B35, B36 review | None | Four triggers, a history of each, and a "Reviewed" note. Blocks nothing. |
| B37–B40 Project officer | Roles: Administrator, Data steward, Placement officer, Manager, M&E analyst, Assessor, … No Project officer role | A new role: Placement officer permissions minus `ydm.assess`, plus identifiable export (§3.3). Imports limited to its scope. |
| B39 unassigned youth | 1 of 78 dev participants has no enrollment | A Self-Registration Queue for all-scope roles. |
| B41 shared employers | Employers and opportunities are already global | **Already met.** |
| B42 portal | The portal shows referrals only (portal/services.py:300–311) | **Already met.** Keep it. |
| A2 retention | `apps/retention` exists: per data class, a period and an approval; nothing is reduced without both | Register the new data classes **with no period**. Nothing is deleted until the DPO approves a period. Unlimited retention is not hard-coded. |

## 3. Conflicts with today's design

### 3.1 B1: rename "Programme" to "Project" everywhere
This is the largest change. Earlier plan acceptance criterion AC-A1 said "API unchanged", and it is now **reversed**.
- **Database:**
  - `RenameModel` and `RenameField` migrations keep the data and only change names. Tables are renamed in the same migration.
  - Foreign-key fields are renamed: `Cohort.programme`, `ParticipantEnrollment.programme`, `Course.programme` (removed by B2 anyway).
- **Stored values:** `ScopeAssignment.kind = "programme"` becomes `"project"` through a data migration. So does the scope-map key. This step is security-relevant: if it is missed, every Project officer sees nothing (deny-by-default), which fails safe.
- **API:** field names and URL segments change in one release. The React frontend is the only client, so no transition aliases are planned. **This is our technical choice;** say if an outside system calls the API.
- **Audit history is not rewritten.** Old audit events keep the word "programme" as they were recorded. The history must not be changed.
- **Imports:** headers accept both "Programme" and "Project" so that old spreadsheets still load.
- **Order:** do the rename **first**, before the other schema changes, so new code is written once with the new names.
- **Effort:** about 8–10 days, up from 1 day for labels only.

### 3.2 B28: one active placement per youth
- **Today:** a second running placement is allowed.
- **New rule:** the service refuses a new active placement while one is running. The officer ends the old one first, or uses "changed employer", which ends the old one and starts the new one in one step.
- **Database guard:** a partial unique constraint (one row per participant with `end_date IS NULL`). This needs a pre-check: the dev database has **0** participants with more than one running placement. The shared database must be checked too (D-035).
- **C-3, imports:** an import row that would create a second active placement either (a) goes to review as "Needs Review" without being created, or (b) ends the earlier one. **Our proposal is (a)**, because (b) changes history without a person deciding. CAP-YEI must confirm.
- The synthetic seed already ends the first job before starting the second, so it stays valid.

### 3.3 B40: identifiable export for Project officers
- **Today:** `exports.identifiable` is **grant-only**. By design it "can never be put in a role" (identity/catalogue.py:3). It is given to a named user, with a stated purpose, and audited.
- **The answer:** Project officers may export identifiable data, limited to their projects.
- **C-2, options:**
  - **(a) Keep the grant-only design.** An administrator grants the export to each Project officer by name. It works today, with no security-model change.
  - **(b) Make the permission role-assignable** and put it in the Project officer role.
  - **Our recommendation is (a)**, because it meets the answer without weakening a deliberate control. (b) is a security-design change that the PI360 owner must approve.
- **Either way:** exports are filtered by scope (scenario 10) and audited.
- **Also note:** Placement officers do not have identifiable export today. B37 ("same as Placement officer") together with B40 gives Project officers *more* than Placement officers, which is worth stating to CAP-YEI.

### 3.4 B34 and scenario 9: duplicates without an approval gate
- The old design avoided duplicates through officer approval. That gate is now removed.
- **Replacement:**
  - At sign-up, run the existing duplicate check (`participants/duplicates.py`).
  - On a likely match, create the account and flag "Needs Review (possible duplicate)" instead of blocking.
  - Officers merge from the queue.
- The sign-up response never says whether a match exists.
- Scenario 9 becomes: "a likely duplicate is flagged and can be merged; no data is shown to the applicant."

### 3.5 B9: availability is independent of employment
- The earlier proposal (placed means closed by default) is **reversed**.
- Never-placed youth default to Open.
- **C-1:** the source does not say what the default is for youth who are placed now or were placed before, only that they "can mark themselves Open". **Our proposal:** keep their status as Open unless they or an officer close it. That is one simple rule, and employment never closes it.

### 3.6 B24: "suspended employers"
- B24 says suspended employers are excluded from recommendations.
- **C-4:** but PI360 has no suspended status (Employer: active / inactive / prospect), and B23 approved only Monitor and Ignore as outcomes.
- **Our proposal:** treat **Inactive** as excluded, which it should be already, and add no new suspension.
- The "matching penalty" for poor ratings has no agreed size. Until it does, build the **quality warning only**.

### 3.7 B14, B16 and B37: Project officers and assessments
- B37 says a Project officer equals a Placement officer.
- B14 and B16 explicitly leave Project officers out of assessment editing.
- **We apply the specific rule:** no `ydm.assess` for Project officers, and "view" only if CAP-YEI confirms.

### 3.8 B15: no completeness threshold
- The earlier plan hid totals below a minimum completion (AC-D2). That was not approved.
- **New rule:** always show the score from completed criteria, with "n of 26 criteria completed".

## 4. Migrations and data risks (in order)

| # | Migration | Kind | Risk | Guard |
|---|---|---|---|---|
| M1 | Programme → Project (models, fields, tables, scope kind) | Rename + data | Scope rows missed, so officers see nothing | Count scope rows before and after; isolation suite |
| M2 | Course becomes global (drop `programme`, unique `code`) | Three-step | Code clashes | Read-only clash report; dev has 1 clash with the **same** name (the synthetic SYN-HOSP), which merges cleanly |
| M3 | One active placement constraint | Constraint | Existing doubles | Pre-check count (dev: 0) |
| M4 | Disability, review, availability, follow-up, feedback, self-employment fields | Additive | Low | Forward and back tests |
| M5 | Assessments module | New tables | Low | — |
| M6 | Project officer role, permission data | Data | Over-granting | Permission-matrix test |
| M7 | Go Blue disability import (historical) | Import | Sensitive values | Only after D-090 enablement; blank stays "not recorded" |

Every migration is preserved and reversible. The rename uses no drop-and-recreate.

## 5. Revised phases

| Phase | Content | Waits for |
|---|---|---|
| **1. Foundations** | M1 rename (backend, API, frontend, imports, help guides); Project officer role and isolation suite; bulk verification; review flag (four triggers) | C-2 for export only |
| **2. Placements and availability** | M3 one active placement plus "changed employer"; follow-up outcomes, types, reasons, salary, self-employment; Open for Opportunities with history and matching exclusion; exit feedback with confidentiality per record | C-1, C-3 |
| **3. Courses, disability, self-registration** | M2 shared courses plus Go Blue courses 001–007; disability field with audited access; self-registration with duplicate flagging and queue | D-090 before switching on for real youth; the setup sheet (B3) when import starts |
| **4. Assessments and employer quality** | Assessment instrument (26 criteria, 1–5, averages, history); employer rating scale, alerts and review outcomes; employer-quality warning; B-COMP factor built with its weight unset | B18 weight, B19 criteria, A6 minimum count (aggregates stay off) |
| **5. Reporting and UAT** | Metrics labelled "not approved" until B43; retention 3/6/12 months split two ways; Playwright scenarios; UAT | B43 |

Privacy rule for every phase: features with new sensitive data can be built and tested on synthetic data now. They are **switched on for real youth only after the DPO confirms A2/D-090**.

## 6. Not approved: do not build as requirements
- A minimum rating count before employer aggregates show (A6 is pending; the feature stays off).
- A dedicated `participants.verify` permission. We use existing permissions on the three approved roles, unless CAP-YEI asks for one.
- A mandatory reason for an individual skill rejection. The field is optional.
- A batch reference for bulk verification. It is kept only as an internal audit id, not a feature.
- Reminders for old availability statuses.
- A versioned correction workflow and an approval step for assessments. We keep history (B15 point 5) but add no approval.
- Competency matching weights.
- Discussing with the employer, or pausing referrals, as review outcomes.

## 7. Clarifications to send back to CAP-YEI

| # | Question | Our proposal |
|---|---|---|
| C-1 | Open for Opportunities: default for youth placed now or placed before? | Open unless they or an officer close it. |
| C-2 | Identifiable export for Project officers: grant per person (today's control), or put it in the role? | Grant per person. |
| C-3 | An import would create a second active placement: hold it for review, or end the earlier one? | Hold for review. |
| C-4 | "Suspended employers": there is no suspension in PI360. Is Inactive enough? | Yes, Inactive; no new status. |
| C-5 | May Project officers *view* assessments (they may not edit)? May youth view their own scores (B14)? | Project officers view; youth: CAP-YEI decides. |
| C-6 | Pending from the source: B16 approval step, B17 interval, B18 weight, B19 criteria, A6 minimum count, B30 position, B43 metrics, A2 DPO confirmation | — |
