# CAPYEI meeting of 23 November 2026: decision and clarification register

**PI360** · Planning document · 23 Nov 2026 · Status: **answers received 23 Nov 2026**. 18 of D-070 to D-090 are now Decided; D-077, D-089 and D-090 stay Open. See §0.

## 0. Answers received (23 Nov 2026)

CAP-YEI and the DPO answered the decision pack. The user passed on the consolidated answers on 23 Nov 2026. The answers are recorded in `../planning/registers/decisions.csv` (columns "Decision made" and "Decided by / date").

Where an answer differs from a recommendation in §3, **the answer wins**. §3 is kept unchanged as the record of what was asked. The impact on the code, the conflicts and the revised phases are in `docs/capyei-answers-impact-assessment.md`.

| Status | Decisions |
|---|---|
| **Decided** | D-070, D-071, D-072, D-073, D-074, D-075, D-076, D-078, D-079, D-080, D-081, D-082, D-083, D-084, D-085, D-086, D-087, D-088. Older: D-052, D-054, D-065. |
| **Open, partly answered** | D-077 (criteria B19 and the employer aggregate minimum A6 pending), D-089 (metrics; "§5.13" was a broken reference, see `docs/capyei-metric-definitions.md`), D-090 (DPO confirmation pending). Older: D-053, D-055, D-056, D-057, D-062, D-063, D-066. |

Answers that **reverse** a recommendation in §3:
- **D-070:** rename in the database and API too, not only on screens.
- **D-073:** employment never closes Open for Opportunities. Never-placed youth default to Open.
- **D-075:** only Administrators and Placement officers record assessments. Trainers, Assessors and Project officers do not.
- **D-077:** employers may see aggregates (A6), once a minimum count is set.
- **D-078:** the review outcomes are Monitor or Ignore only.
- **D-081:** one active placement, not concurrent ones.
- **D-082:** Yes/No only, with no "Prefer not to say". An optional description if Yes.
- **D-083:** no officer approval before the account works. Verification is mandatory only after the pilot.
- **D-085:** Project officers may import and export identifiable data in their projects.

Clarifications sent back (C-1 to C-6) are listed in the impact assessment §7.

These are the questions CAP-YEI must answer before the meeting requirements can be built as specified. Each has a recommended option. A recommendation is **not** a decision. Do not build behaviour that depends on an option until the named approver has chosen it in writing.

## Numbering and relationship to the main register

- The main register is `../planning/registers/decisions.csv` and `../planning/12_Client_Clarification_and_Decision_Register.md`. Its last ID is D-069.
- The items below use **D-070 to D-090**. These are proposed numbers and have **not** been added to `decisions.csv`. When the pack goes to CAP-YEI, add them there with status `Open`.
- Existing decision statuses are unchanged. The ones this work depends on are listed in §2 as they stand today:
  - **Decided:** D-009, D-012, D-013, D-028.
  - **Proposed:** D-015.
  - **Open:** D-001, D-006, D-007, D-008, D-014, D-016, D-024, D-027, D-052 to D-058, D-063, D-065.
- Task IDs (PI360-NEW-xxx) refer to `docs/capyei-implementation-backlog.md`.

## 1. Summary

| ID | Topic | Priority | Approver | Blocks |
|---|---|---|---|---|
| D-070 | "Programme" to "Project": wording only or a database rename | High | CAP-YEI placement lead (wording); tech lead (schema) | NEW-004, NEW-005 |
| D-071 | Course independence and the Go Blue structure | High | CAP-YEI placement lead + data steward | NEW-006 to NEW-009 |
| D-072 | Bulk skills verification policy | Medium | CAP-YEI placement lead | NEW-010 to NEW-013 |
| D-073 | "Open for Opportunities" behaviour | High | CAP-YEI placement lead | NEW-014 to NEW-018, NEW-052 |
| D-074 | Trainer competency instrument (relation to YDM/IYLDP) | Critical | CAP-YEI programme lead + training lead | NEW-019 to NEW-025, NEW-030 to NEW-032 |
| D-075 | Who assesses, reassesses and amends | High | CAP-YEI training lead | NEW-022 to NEW-024 |
| D-076 | Trainer assessment in matching | Critical | CAP-YEI placement lead (D-009 approver) | NEW-030 to NEW-032 |
| D-077 | Employer rating criteria, scale and visibility | High | CAP-YEI placement lead | NEW-026, NEW-027, NEW-029 |
| D-078 | Employer performance alert thresholds and review outcomes | High | CAP-YEI placement lead | NEW-028 |
| D-079 | Exit feedback: who submits and how | High | CAP-YEI placement lead + DPO | NEW-039, NEW-053 |
| D-080 | Follow-up data requirements (salary, types, reasons, retention meaning) | High | CAP-YEI placement lead + M&E + DPO (salary) | NEW-034 to NEW-038, NEW-064 |
| D-081 | Multiple concurrent placements | Medium | CAP-YEI placement lead | NEW-036 |
| D-082 | Disability field: wording, values, position, whether held | Critical | CAP-YEI + DPO (with D-063) | NEW-040 to NEW-043 |
| D-083 | Youth self-registration and verification | Critical | CAP-YEI sponsor + DPO (with D-006) | NEW-044 to NEW-049 |
| D-084 | "Needs Review" / "Reviewed" meaning | Medium | CAP-YEI placement lead | NEW-050, NEW-051 |
| D-085 | Project Officer permissions and edge cases | Critical | CAP-YEI sponsor (with D-014) | NEW-056, NEW-057, NEW-059 to NEW-061 |
| D-086 | Employer and opportunity project association | High | CAP-YEI placement lead | NEW-058 |
| D-087 | Employer quality in recommendations | Medium | CAP-YEI placement lead (with D-027) | NEW-033 |
| D-088 | Portal "suitable opportunities" for youth | High | CAP-YEI sponsor (with D-006/D-007) | NEW-054 |
| D-089 | New dashboard metric definitions | Medium | CAP-YEI M&E lead | NEW-062 to NEW-064 |
| D-090 | Data-protection addendum for the new data | Critical | CAP-YEI DPO | Production use of NEW-019+, NEW-026+, NEW-034+, NEW-040+, NEW-044+ |

## 2. Existing decisions this work depends on (status as before the answers; see §0 for D-052, D-054, D-065 now Decided)

| ID | Status today (from `decisions.csv` / PROJECT.md) | Why it matters here |
|---|---|---|
| D-001, D-052 to D-058, D-065 | Open | YDM/IYLDP instrument, scale, weights, missing answers, roles, import. The trainer rating is the same instrument family (D-074). |
| D-006, D-007 | Open | Self-service scope and direct application. These bear on self-registration (D-083) and portal opportunities (D-088). |
| D-008 | Open | Mandatory vs preferred factors. Trainer ratings must not become a hidden mandatory filter (D-076). |
| D-009 | Decided: the Administrator approves rule versions for now | A new rule version that adds a competency factor goes through this approval. Weights are still not set. |
| D-012, D-028 | Decided: follow-ups at 30 d, 90 d, 6/12/24 m | Kept as they are. Follow-up outcomes (D-080) attach to these milestones. |
| D-013 | Decided: show employer indicators with the count, hide below a minimum (starts at 5) | Employer ratings use the same rule (D-077). |
| D-014 | Open | Record scope rules. The Project Officer (D-085) is a concrete answer to part of it. |
| D-015 | Proposed, not final. Production import blocked. | New personal data needs the DPO's addendum (D-090). |
| D-016 | Open | E-mail/SMS provider. Verification messages need it (D-083). |
| D-024 | Open | Role catalogue, including the Assessor role (inactive today). |
| D-027 | Open (recommendation: indicator profile, no composite) | Employer "average rating" must stay per criterion, with counts (D-077, D-087). |
| D-063 | Open | Which sensitive fields may be held, including disability (D-082). |

## 3. Decisions

### D-070: "Programme" to "Project": wording only, or a database rename?

- **Topic:** Projects and cohorts (requirement A1–A2).
- **Question:** Should "Programme" become "Project" only in what people see, or should the database tables and API fields be renamed too?
- **Why it matters:**
  - "programme" appears in the `Programme` model and the `programme` FKs on Course, Cohort and ParticipantEnrollment.
  - It is also the scope kind `programme` (stored in ScopeAssignment rows), the participant `scope_map`, the import column `programme_code`, report filters, OpenAPI and roughly 30 frontend files.
  - A database rename touches every one of these and the audit history keys. A wording change touches only labels.
- **Options:**
  - (a) **Wording only:** labels, help guides, report titles and import template headers say "Project". Code, database and API keep `programme`.
  - (b) **Wording plus API aliases:** as (a), and the API also accepts and returns `project`/`project_id` beside `programme`. `programme` is marked deprecated.
  - (c) **Full rename:** rename the model, tables, FKs, scope kind and API fields in one migration.
- **Consequences:**
  - (a) Cheapest and no data risk. Developers and API consumers still see "programme".
  - (b) Small extra cost. External consumers can move to the new name at their own pace.
  - (c) Several days of work and a data migration of ScopeAssignment values. It changes the audit keys going forward (old entries keep the old keys) and breaks existing API clients and saved import templates. No user-visible benefit over (a).
- **Recommendation:** (a) now. Add (b) only if an external consumer of the API exists. Never (c) during the pilot.
- **Blocks:** NEW-004, NEW-005.
- **Approver:** CAP-YEI placement lead for the wording; PI360 tech lead for the schema choice.

### D-071: Course independence and the Go Blue Excel structure

- **Topic:** Projects and cohorts (A2–A4).
- **Question:** Can courses exist on their own (a shared catalogue), linked to projects only through cohorts? What exactly is the Go Blue hierarchy and wording?
- **Why it matters:**
  - Today `Course` has a required FK to `Programme` and its code is unique per programme (`configuration/models.py`, `uniq_course_code`).
  - Making courses independent removes that FK. Two programmes may already hold courses with the same code but different meanings, and these must be resolved.
  - The Go Blue workbook (meeting notes said "GoBrew") shows the hierarchy; only the setup sheet CAP-YEI uses for a new project is still missing.
- **Options:**
  - (a) **Global course catalogue:** a course is defined once. A cohort offers courses through the existing `CohortCourse` link. Course codes are unique across the system.
  - (b) **Keep courses under projects** and only hide the project in the UI.
  - (c) **Global catalogue plus optional "default project"** as a filter hint only.
- **Consequences:**
  - (a) Matches the request. Needs a data check for code clashes before the migration (a read-only report, NEW-006a). The import must look courses up by code alone.
  - (b) No migration, but it does not meet the request. The same course will be duplicated for every project.
  - (c) As (a), with a convenience filter. It risks being read as ownership again.
- **Recommendation:** (a), after CAP-YEI sends a Go Blue sample (synthetic or redacted) and the clash report has been reviewed.
- **Phase 0 finding (23 Nov 2026, read-only, headers and counts only):**
  - "GoBrew" in the meeting notes is **Go Blue** (confirmed 23 Nov 2026). Source: `documents/Go Blue Trainee Placement Data.xlsx`.
  - Go Blue numbers its 7 courses (001–007) across the whole programme and offers them in 36 cohorts at 9 centres (73 offerings). This is a shared course list, which today's per-programme `Course` cannot hold without duplicating courses.
  - Details: `docs/capyei-decision-pack.md` Part C.
- **Blocks:** NEW-006, NEW-007, NEW-008, NEW-009.
- **Approver:** CAP-YEI placement lead and data steward.

### D-072: Bulk skills verification policy

- **Topic:** Skills verification (B).
- **Questions:**
  - Who may verify skills in bulk?
  - Which outcomes can be applied in bulk?
  - Is one method and one evidence note enough for a whole batch?
- **Why it matters:**
  - Today verification goes one entry at a time.
  - "Verified" needs a method and "Rejected" needs notes (`participants/profile.py`).
  - The permission is the broad `participants.edit`.
  - Bulk use can turn verification into a rubber stamp.
- **Options:**
  - (a) Bulk **Verified** and **Needs reassessment** only. Rejection stays one at a time. Each batch has one method and one shared note.
  - (b) All outcomes in bulk, rejection included, with one shared note.
  - (c) Bulk only within one youth (many skills), never across youth.
- **Consequences:**
  - (a) Fast for the common case (a cohort verified after a practical test). Rejection keeps an individual reason.
  - (b) Rejections would carry a generic reason, which is weaker evidence.
  - (c) Safest, but does not meet "many youth at once".
- **Recommendation:**
  - (a), supporting both many skills for one youth and one skill across many youth.
  - Add a new permission `participants.verify`, separate from `participants.edit`, and give it to the Placement officer and Project officer roles.
  - Set a batch limit (proposed 200 entries; this is a technical setting).
- **Blocks:** NEW-010 to NEW-013.
- **Approver:** CAP-YEI placement lead.

### D-073: "Open for Opportunities" behaviour

- **Topic:** Availability (C).
- **Questions:**
  - What does the flag mean for each employment situation?
  - Who may change it?
  - Can an officer override the youth?
  - Does it expire?
  - How does it affect matching and existing referrals?
- **Why it matters:**
  - Today there is no availability flag, and `intelligence.suggest_youth` does not exclude placed youth.
  - Employment status is derived from Placement episodes and must not be mixed up with availability.
- **Options:**
  - (a) **Flag defaults by situation:**
    - Never placed, exited or unemployed: open by default.
    - Currently placed: closed by default.
    - Youth and officer may both change it, and the latest change wins, recorded with who and why.
    - Matching excludes "closed" youth from suggestions.
    - Existing referrals stay active, and the officer is warned.
  - (b) Same as (a), but the officer cannot change a youth's own choice (the youth decides).
  - (c) Matching ranks closed youth lower instead of excluding them.
  - Separate choice: whether the flag expires (for example, it must be reconfirmed every 90 days) or never expires.
- **Consequences:**
  - (a) Clear and auditable. It respects scenario 4 (a placed youth who is not open is excluded).
  - (b) Respects youth autonomy. Officers lose the ability to correct stale flags for youth who cannot use the portal.
  - (c) Weaker privacy: a placed youth who did not ask may still be put forward.
  - Expiry stops stale "open" flags but adds reminder work.
- **Recommendation:**
  - (a), with an officer override that requires a reason. The youth sees the latest value and who set it ("set by your officer").
  - No expiry in the pilot. Report flags older than a configurable number of days instead (setting `availability.stale_days`, value for CAP-YEI to set).
  - Existing referrals are never withdrawn automatically.
- **Blocks:** NEW-014 to NEW-018, NEW-052.
- **Approver:** CAP-YEI placement lead.

### D-074: Trainer competency instrument: is it the YDM/IYLDP?

- **Topic:** Youth ratings (D).
- **Question:** The meeting's competencies are Time management, Communication, Interpersonal skills, Maturity, Leadership and Personality/attitude. Is this the same instrument as the IYLDP/YDM template already analysed in `planning/16_YDM_Assessment_Specification.md`?
- **Why it matters:**
  - The six categories match the IYLDP categories exactly, and that template has 26 criteria.
  - If the two are the same, D-001 and D-052 to D-058 (scale, meaning, weights, missing answers, roles, import) must be answered once, not twice.
  - D-065 asks whether YDM is pilot scope at all. The meeting request is evidence of intent, but it is not a written scope change.
- **Options:**
  - (a) One configurable assessment framework, with the IYLDP as its first template. "Trainer rating" is the user-facing name.
  - (b) A separate simpler "trainer rating" (six scores, 1–5) beside a future YDM module.
  - (c) Defer until D-001 closes.
- **Consequences:**
  - (a) One model, one set of decisions. It needs D-052 (scale), D-054 (weights) and D-055 (missing answers) before scores can be shown.
  - (b) Duplicate data and workflows. This is the duplication the brief warns against.
  - (c) Delays requirements D and E.
- **Recommendation:**
  - (a). Build the framework with templates, scales and weights as configuration.
  - Ship it with **no default scale and no weights**. A template cannot be activated until its scale and scoring method are entered and approved.
  - CAP-YEI also confirms D-065 in writing.
- **Blocks:** NEW-019 to NEW-025, NEW-030 to NEW-032.
- **Approver:** CAP-YEI programme lead and training lead.

### D-075: Who assesses, reassesses and amends?

- **Topic:** Youth ratings (D).
- **Questions:**
  - Who records an assessment: trainer, development officer, or both?
  - Is a second person needed to submit it?
  - How often is a youth reassessed?
  - Can a submitted assessment be corrected?
- **Why it matters:**
  - Sets the permissions (`ydm.assess`, `ydm.manage`), the Assessor role (inactive until D-024) and the history rules.
  - Overlaps D-056.
- **Options:**
  - (a) A trainer or development officer records and submits. A correction is a new assessment that supersedes the old one, which is kept.
  - (b) Recorded by a trainer and approved by a supervisor.
  - (c) Free editing of submitted assessments.
- **Consequences:**
  - (a) Simple, with full history.
  - (b) Stronger control, but adds a queue.
  - (c) Loses history and is not acceptable for audit.
- **Recommendation:** (a). Activate the Assessor role (D-024), scoped to assigned projects or cohorts. Reassessment is on demand, and an optional reminder interval is a setting with no default value.
- **Blocks:** NEW-022 to NEW-024.
- **Approver:** CAP-YEI training lead.

### D-076: How do trainer assessments influence matching?

- **Topic:** Matching (E).
- **Questions:**
  - Is the competency result a preferred factor (adds to the weighted score), a mandatory factor (can make a youth ineligible), or display-only?
  - What weight does it carry?
  - What happens when a youth has no assessment?
- **Why it matters:**
  - Principles E2–E5: mandatory qualifications stay hard constraints, and trainer ratings must not replace technical qualifications.
  - All weights are still undecided (D-008, D-009). Today the UI shows "Preferred X of Y" because no weights are approved.
- **Options:**
  - (a) **Preferred factor only (B-COMP):**
    - It passes when the latest submitted total or a named category meets a threshold set on the opportunity or rule.
    - Weight `w_comp` is set by the Administrator in a new rule version.
    - Unknown policy: "unknown" (shown as "No assessment") and never a fail.
  - (b) Allow employers to make a competency threshold mandatory.
  - (c) Display only: shown beside the match, not scored.
- **Consequences:**
  - (a) Meets E1–E8. Interim display stays "Preferred X of Y" until weights are approved.
  - (b) A youth without an assessment could be shut out of jobs, which is a fairness risk (D-034).
  - (c) Safest, but does not meet the request.
- **Recommendation:**
  - (c) until the instrument is approved (D-074).
  - Then (a), as a new draft rule version approved under D-009.
  - Never (b) in the pilot.
- **Blocks:** NEW-030 to NEW-032.
- **Approver:** CAP-YEI placement lead (rule approver per D-009).

### D-077: Employer rating criteria, scale and visibility

- **Topic:** Employer ratings (D).
- **Questions:**
  - Are the five proposed criteria final: work environment, management and supervision, treatment and respect, working conditions, overall experience?
  - Is the scale 1–5, and what does each point mean?
  - Who may see the ratings?
- **Why it matters:**
  - `EmployerFeedback` already holds a single 1–5 rating per record (party employer or youth). The setting `employer.positive_rating` is 4 and `employer.min_feedback` is 5.
  - Per-criterion scores extend this record rather than duplicating it.
  - D-027 (no composite score) is still open.
- **Options:**
  - (a) Five criteria, 1–5, labelled points. Staff see per-criterion averages with counts, hidden below `employer.min_feedback`. Employers never see individual ratings, and see no aggregate in the pilot.
  - (b) As (a), but employers see their own aggregate when n ≥ minimum.
  - (c) The single overall rating only.
- **Consequences:**
  - (a) Protects youth: a small employer could guess who rated them.
  - (b) Useful feedback to employers, but a re-identification risk when n is small.
  - (c) Loses the breakdown CAP-YEI asked for.
- **Recommendation:** (a). Revisit (b) after the pilot, with the DPO.
- **Blocks:** NEW-026, NEW-027, NEW-029.
- **Approver:** CAP-YEI placement lead.

### D-078: Employer performance alerts and review

- **Topic:** Employer ratings (D).
- **Questions:**
  - What counts as negative feedback, for example any criterion ≤ 2?
  - How many negatives within what period trigger an administrative review?
  - What review outcomes exist?
- **Why it matters:** CAP-YEI requires "no automatic suspension". The thresholds are business rules and must be settings, not code.
- **Options:**
  - (a) Two settings:
    - `employer.alert_rating`: a criterion score at or below this is negative.
    - `employer.alert_count`: this many negatives within `employer.window_days` opens a review.
    - Review outcomes: no action, monitor, discuss with employer, pause new referrals (a manual action with a reason).
  - (b) Alert on every negative rating.
  - (c) No alerts. Reports only.
- **Consequences:**
  - (a) Proportionate and auditable.
  - (b) Noisy.
  - (c) Misses serious issues such as safety.
- **Recommendation:** (a), with values left empty until CAP-YEI sets them. Until then no alert fires and the screen says so. A free-text safeguarding concern always goes to the support process, not to ratings.
- **Blocks:** NEW-028.
- **Approver:** CAP-YEI placement lead.

### D-079: Exit feedback: who submits, through which channel, and what employers see

- **Topic:** Exit feedback (G).
- **Questions:**
  - Can youth submit exit feedback in the portal?
  - Can officers record it on their behalf?
  - Is it one form per placement?
  - Is it confidential from the employer?
- **Why it matters:** Feedback is personal data about the youth's experience. It feeds employer indicators and must not be traceable by the employer.
- **Options:**
  - (a) Youth in the portal **or** officer-assisted (marked "assisted"). One exit feedback per placement episode. Never shown to the employer individually.
  - (b) Officer-recorded only.
  - (c) Youth portal only.
- **Consequences:**
  - (a) Highest coverage. Needs the portal form and privacy notice text (D-090).
  - (b) Lower coverage and more officer time.
  - (c) Excludes youth without data access.
- **Recommendation:** (a).
- **Blocks:** NEW-039, NEW-053.
- **Approver:** CAP-YEI placement lead and DPO.

### D-080: Follow-up data requirements

- **Topic:** Follow-ups (F).
- **Questions:**
  - Is salary recorded, and if so as an amount, a band, or not at all?
  - What are the lists for employment type and reasons for leaving?
  - Does "retained" mean with the same employer, or in any employment?
  - Does self-employment count as a placement outcome?
- **Why it matters:**
  - Salary is sensitive and not held today.
  - `Placement` has no salary or employment-type field.
  - `followups.retention_counts` currently means "still employed" at the 90-day step.
  - Two retention meanings give two different numbers.
- **Options:**
  - **Salary:**
    - (a) a band from a configured list;
    - (b) an exact amount and currency;
    - (c) not collected.
  - **Retention:**
    - (i) report both "retained with the same employer" and "in employment (any)";
    - (ii) one meaning only.
- **Consequences:**
  - Bands lower the sensitivity and are enough for reporting.
  - Exact amounts need DPO approval and restricted access.
  - Reporting both meanings avoids arguments about the number.
- **Recommendation:**
  - Salary as a band, collected only after D-090.
  - Employment type and leaving reasons as editable reference lists.
  - Report both retention meanings.
  - Self-employment is its own outcome, counted as "in employment" but not as "same employer".
- **Blocks:** NEW-034 to NEW-038, NEW-064.
- **Approver:** CAP-YEI placement lead, M&E lead, and the DPO for salary.

### D-081: Multiple concurrent placements

- **Topic:** Follow-ups and placements (F).
- **Question:** Can a youth hold two running placements at once, for example a part-time job plus self-employment?
- **Why it matters:**
  - Today a second running episode is allowed, with a duplicate warning only for the same employer (`placements.running_with_employer`).
  - A follow-up "changed employer" must know whether to end the old episode.
- **Options:**
  - (a) Allowed. "Changed employer" ends the old episode by default, and the officer can keep both running.
  - (b) Only one running episode. A new one always ends the old.
- **Consequences:**
  - (a) Reflects real life but makes counting more complex: count youth, not episodes.
  - (b) Simpler, but wrong for concurrent work.
- **Recommendation:** (a). This matches current behaviour.
- **Blocks:** NEW-036.
- **Approver:** CAP-YEI placement lead.

### D-082: Disability field: wording, values, position and whether it is held

- **Topic:** Disability (H).
- **Questions:**
  - May PI360 hold disability information at all? (This is part of D-063.)
  - What exact wording and answer options?
  - Can the youth self-declare it?
  - Where does the field go?
- **Why it matters:**
  - Disability is not collected today. Reports list it as "not collected" (`reporting/services.py`, `reporting/reports.py`).
  - It may exist only in import source columns kept in `ParticipantEnrollment.extra`. This needs a read-only check against real data, which is not done here.
  - The meeting action item says **"After Jeddah"**, but the discussion says **after Gender**. "Jeddah" is not a field on any PI360 form; the add-youth form has Gender, then Status, then Home county. This looks like a transcription error, but it must be confirmed.
- **Options:**
  - **Values:**
    - (a) Yes / No / Prefer not to say, with an unrecorded "Not recorded" state;
    - (b) as (a) plus a type list (for example, the Washington Group short set);
    - (c) free text (not recommended).
  - **Access:** visible to staff with `participants.view`, or restricted behind a grant like `restricted.view_background`.
- **Consequences:**
  - (b) gives better reporting but is more sensitive.
  - Restricting access protects the youth, but hides it from officers who need it for reasonable adjustments.
- **Recommendation:**
  - (a). Put it right after Gender, subject to confirming the "Jeddah" wording.
  - Visible in the youth profile only to roles granted a new `participants.view_disability` permission.
  - Reports show only aggregates, with small-cell suppression (`exports.small_cell`).
  - Historical records stay "Not recorded". Nothing is inferred.
  - Nothing is collected until D-063 and D-090 allow it.
- **Blocks:** NEW-040 to NEW-043.
- **Approver:** CAP-YEI and the DPO.

### D-083: Youth self-registration and verification

- **Topic:** Registration (I).
- **Questions:**
  - Should youth be able to sign up without an invitation?
  - How are they verified: e-mail, phone, or both?
  - Does every sign-up need officer approval?
  - What does the applicant see if they match an existing record?
- **Why it matters:**
  - The portal is invite-only today (`portal/services.send_invite`, `activate`).
  - Go Blue imported youth already have records, and a sign-up must not create a duplicate (scenario 9).
  - SMS needs a provider (D-016).
  - Self-service scope itself is D-006, still open.
- **Options:**
  - (a) **Request-then-approve:**
    - Sign-up creates a *registration request*, not a youth record.
    - The applicant verifies e-mail (and phone once SMS exists).
    - An officer reviews suggested matches and either links the request to the existing record, creates a new record, or rejects it.
    - The account is then activated through the existing activation flow.
  - (b) Automatic record creation after verification, with duplicate checks run afterwards.
  - (c) Stay invite-only, plus an "ask for an invitation" form.
- **Consequences:**
  - (a) No duplicates, and no disclosure to the applicant about existing records. Needs an officer queue.
  - (b) Duplicates and merge work. Real risk of account takeover of an existing record.
  - (c) Least work, but does not meet "sign-up with verification".
- **Recommendation:**
  - (a), behind a feature flag that is off until the DPO approves the notice and consent text (D-090).
  - The applicant never learns whether a matching record exists. Responses are always generic.
- **Blocks:** NEW-044 to NEW-049.
- **Approver:** CAP-YEI sponsor and DPO.

### D-084: Meaning of "Needs Review" and "Reviewed"

- **Topic:** Youth status (J).
- **Questions:**
  - What makes a youth "Needs Review"?
  - Who may mark them "Reviewed"?
  - Does "Needs Review" block anything?
- **Why it matters:** These must not collide with `Participant.status` (active/completed/withdrawn/unknown), enrollment status, placement status or skill verification status.
- **Options:**
  - (a) A separate review flag:
    - Set by events: new self-registration linked, youth self-edit of key fields, import update changing key fields, an officer flag with a reason.
    - Cleared by any officer with `participants.edit` in scope, using "Mark reviewed", alone or in bulk.
    - It blocks nothing; it is a work queue.
  - (b) As (a), but "Needs Review" youth are excluded from matching.
  - (c) Make it a new value of `Participant.status`.
- **Consequences:**
  - (a) No conflict with the lifecycle.
  - (b) Can hide youth from opportunities for administrative reasons.
  - (c) Mixes two meanings and breaks reports that use status.
- **Recommendation:** (a). CAP-YEI confirms the list of trigger events.
- **Blocks:** NEW-050, NEW-051.
- **Approver:** CAP-YEI placement lead.

### D-085: Project Officer permissions and edge cases

- **Topic:** Access (L).
- **Questions:**
  - What may a Project Officer do?
  - How are the edge cases handled?
    - youth in two projects;
    - records with no project;
    - employers and opportunities used by several projects;
    - exports;
    - imports.
- **Why it matters:**
  - The mechanism already exists:
    - `Role.scope_mode = "assigned"` plus `ScopeAssignment(kind="programme")`;
    - values OR'd within a kind, kinds AND'd;
    - no assignment means deny;
    - out-of-scope records return 404.
  - Only the *policy* is new. D-014 (record scope rules) is still open.
- **Options:**
  - (a) **Project officer = Placement officer permissions, scoped to assigned projects:**
    - Plus `participants.verify` and `ydm.assess` if D-075 allows.
    - No `exports.identifiable` unless granted per person.
    - Imports limited to rows of assigned projects.
    - A youth in two projects is visible to officers of either.
    - Records with no enrollment are visible only to all-scope roles, and are listed for the data steward.
  - (b) As (a), but also see youth with no project.
  - (c) A read-only project role.
- **Consequences:**
  - (a) Deny-by-default holds. Orphans become a data-quality task.
  - (b) Leaks unassigned youth to every project officer.
  - (c) Does not meet the request.
- **Recommendation:** (a).
- **Blocks:** NEW-056, NEW-057, NEW-059, NEW-060, NEW-061.
- **Approver:** CAP-YEI sponsor.

### D-086: Should employers and opportunities belong to projects?

- **Topic:** Access (L5, L6).
- **Question:** Should employers and opportunities be shared across all projects, as today, or linked to projects so that Project Officers see only their own?
- **Why it matters:** `Employer` and `Opportunity` have no project link and no `scope_map`, so every staff user with `employers.view` sees them all.
- **Options:**
  - (a) Shared, as today. Officers see all employers and opportunities, but only youth, referrals and placements in their projects.
  - (b) An optional `projects` link on Opportunity. An empty link means shared. Employers stay shared.
  - (c) Both employers and opportunities are project-scoped.
- **Consequences:**
  - (a) No change. Employers serving several projects work naturally.
  - (b) Lets a project keep a restricted opportunity. Needs a migration and scope changes in `employers` and `intelligence`.
  - (c) Breaks shared employers and duplicates them.
- **Recommendation:** (a) for the pilot. Choose (b) only if CAP-YEI names a confidentiality need.
- **Blocks:** NEW-058.
- **Approver:** CAP-YEI placement lead.

### D-087: Employer quality in recommendations

- **Topic:** Matching (E6).
- **Question:** Should employer evidence (ratings, retention, response) change the order in which opportunities are suggested to an officer for a youth, and if so how?
- **Why it matters:**
  - E6 asks that employer quality rank employers *separately* from youth competency.
  - D-027 (no composite score) is open, and D-013 hides indicators below the minimum.
- **Options:**
  - (a) A separate "employer evidence" column and sort option. No combined score.
  - (b) A composite employer score used in ranking.
  - (c) No ranking effect.
- **Consequences:**
  - (a) Transparent, and consistent with D-027's recommendation.
  - (b) Hides sparse evidence.
  - (c) Does not meet E6.
- **Recommendation:** (a). Employers below the minimum sort as "insufficient evidence", never as low.
- **Blocks:** NEW-033.
- **Approver:** CAP-YEI placement lead.

### D-088: Portal "suitable opportunities"

- **Topic:** Portal (K).
- **Question:** Should youth see opportunities the system thinks suit them, or only those an officer referred them to, as today?
- **Why it matters:**
  - Today `portal.opportunity` is referral-based.
  - Showing suggestions is self-service matching, which is D-006 and D-007, both open.
  - The privacy boundary forbids showing scores or rejection reasons.
- **Options:**
  - (a) Referral-based only (as today).
  - (b) Show open opportunities that pass all mandatory checks, with no score and no reasons. The youth can "express interest", which creates a draft referral for an officer.
  - (c) Full self-application.
- **Consequences:**
  - (a) No change.
  - (b) More reach. Needs D-006 and D-007.
  - (c) Changes the referral model (D-007).
- **Recommendation:** (a) until D-006/D-007 close, then (b).
- **Blocks:** NEW-054.
- **Approver:** CAP-YEI sponsor.

### D-089: New dashboard metric definitions

- **Topic:** Reporting (M).
- **Question:** Does CAP-YEI approve the definitions in plan §5.13?
  - The definitions include: awaiting review, reviewed and verified, assessed, average assessment score, open for opportunities, employer ratings, changed employers, self-employment transitions, the two retention meanings, referral-to-interview, interview-to-placement and employer responsiveness.
- **Why it matters:**
  - Every metric in `reporting/services.METRICS` carries an `approved` flag, which is false for most.
  - New metrics must say how they are counted and what is missing.
- **Options:** (a) approve as written; (b) amend; (c) defer some.
- **Consequences:** Unapproved metrics still show, labelled "definition not yet approved", as today.
- **Recommendation:** (a) or (b) per metric.
- **Blocks:** NEW-062 to NEW-064, in the sense that the metrics stay labelled "not approved" until then.
- **Approver:** CAP-YEI M&E lead.

### D-090: Data-protection addendum for the new data

- **Topic:** Privacy (cross-cutting).
- **Question:** Under what lawful basis, with what notice wording and for what retention period may PI360 hold the following new data?
  - trainer assessments;
  - employer ratings by youth;
  - exit comments;
  - disability;
  - salary bands;
  - self-registration requests, including rejected ones.
- **Why it matters:**
  - D-015 is still only proposed, and production import is blocked on it.
  - No retention period is set (PROJECT.md).
  - This plan does **not** recommend any basis, notice or period. That is the DPO's decision.
- **Options:** for the DPO.
- **Consequences:** Without it, the features can be built and tested on synthetic data but must stay switched off in production.
- **Recommendation:**
  - Developers prepare an addendum to `docs/data-protection-review.md` describing each new field, who sees it and where it flows (NEW-001).
  - The DPO decides the basis, notice and retention.
- **Blocks:** Production enablement of NEW-019 to NEW-025, NEW-026 to NEW-029, NEW-034 to NEW-039, NEW-040 to NEW-043, NEW-044 to NEW-049, NEW-053.
- **Approver:** CAP-YEI DPO.

## 4. Things that are not decisions but need checking

| Item | What to check | How (read-only) |
|---|---|---|
| Disability in source data | Do Go Blue enrollment `extra` columns hold a disability column, and in what form? | Count of `extra` keys on the dev database. Report key names only, never values. |
| Go Blue wording | Exact column headers and hierarchy in the Go Blue Excel | A synthetic or redacted sample from CAP-YEI |
| Course code clashes | Do any two programmes have courses with the same code but different names? | Read-only query; output codes and counts only |
| Youth without enrollment | How many participants have no enrollment, and would therefore be invisible to a Project Officer? | Read-only count |
| `docs/learner-support-design.md` | Written before follow-ups and the employer portal existed. It schedules 1 w/30/60/90 d/6 m, which conflicts with D-012. | Mark as superseded where it conflicts; do not build from it |
