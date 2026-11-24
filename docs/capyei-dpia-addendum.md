# Data-protection addendum: new data from the 23 November 2026 meeting

**Status:** not reviewed. This continues `docs/data-protection-review.md` (checklist items 1 to 23). It is for the CAP-YEI data-protection officer (DPO) to work through. It is not legal advice, and the developers cannot sign it off.

**Rules this addendum follows:**
- The developers describe the data, who sees it and where it flows.
- The **lawful basis, notice wording and retention period are left blank on purpose**. Only the DPO decides them (D-090).
- None of these features is switched on for real youth until the DPO has answered. Until then they are built and tested on synthetic data only.

Reviewer: ____________  Date: ____________  Outcome: approve / approve with changes / reject

## 0. Answers received (23 Nov 2026)

CAP-YEI and the DPO answered Part A of the decision pack (passed on by the user on 23 Nov 2026). They are recorded below **as given**. The table in §1 is kept as written.

**Still open, and still gating real use:** A2 / D-090. The lawful basis, notice wording and retention period for each row N1 to N8 are still **"DPO"** in §1. Checklist items 24 to 40 are still not reviewed. No feature below is switched on for real youth until the DPO confirms them.

| Row | Answer received | Source |
|---|---|---|
| N1 Assessments | In pilot scope. Recorded by Administrators and Placement officers. Whether youth see their own is pending. | B14, B16 |
| N2 Employer ratings | Scale 1–5. Employers **may** see aggregates, once a minimum count is set (pending). Until then, none. | A6, B20 |
| N3 Exit feedback | Confidentiality stored **per record**; admin default ON; a change applies to new submissions only. | A4 |
| N4 Disability | May be held centrally. The historical Go Blue answers may be imported. Wording given; Yes / No plus optional description; no "Prefer not to say". Access as in the B32 table; **all access logged**. | A1, B31, B32 |
| N5 Salary | Exact amount **and** band may be recorded. | A3 |
| N6 Availability | Youth and officers may change it; employment does not change it. | B9, B10 |
| N7 Self-registration | Allowed without invitation. Draft consent wording given (A5). Rejected requests are **kept until an Administrator deletes them**. Verification by e-mail or phone, mandatory after the pilot. No officer approval. | A5, B33, B34 |
| N8 Review flag | Four triggers; any officer in scope; blocks nothing. | B35, B36 |

**For the DPO to check against these answers** (developers make no recommendation here):
- N7: "kept until an Administrator deletes them" has no end date. Is a maximum retention period needed? This is a DPO decision.
- N4: the historical Go Blue import (A1) brings in answers given under the original Go Blue notice. Does that notice cover PI360? This is a DPO decision.
- N5: an exact salary is more identifying than a band. Confirm who may see the exact amount.
- §2 item 32: the A5 consent wording and the new data may need a new consent version.

## 1. New data, one row each

| # | Data | Purpose | Collected from / by | Who would see it | Flows out? | Lawful basis | Notice wording | Retention |
|---|---|---|---|---|---|---|---|---|
| N1 | **Trainer competency assessment**: score per criterion, optional comment, assessor, date (D-074, D-075) | Show readiness; later an optional, preferred matching factor | Trainer or development officer | Staff with the assessment permission in scope. The youth sees their own (wording to be agreed). Employers never see it. | No. Reports show totals only. | DPO | DPO | DPO |
| N2 | **Employer rating by youth or officer**: five criteria 1–5, note (D-077) | Employer quality evidence | Youth (portal) or officer | Staff with `employers.view`. Averages only, hidden below the minimum count. Employers: none in the pilot. | No | DPO | DPO | DPO |
| N3 | **Exit feedback and comments** at the end of a placement (D-079) | Learn why placements end; employer evidence | Youth (portal) or officer-assisted | Staff in scope. Never shown to the employer individually. | No | DPO | DPO | DPO |
| N4 | **Disability**: Yes / No / Prefer not to say / Not recorded (D-082) | Reasonable adjustments; aggregate reporting | Youth self-declared or officer | Only roles with a new `participants.view_disability` permission. Reports show totals with small-cell suppression. | No identifiable export | DPO | DPO | DPO |
| N5 | **Salary band** at follow-up (D-080) | Outcome reporting | Officer at follow-up | Restricted staff; totals in reports | No identifiable export | DPO | DPO | DPO |
| N6 | **Availability history**: Open / Closed for opportunities, who set it, reason (D-073) | Decide who is suggested for jobs | Youth or officer | Staff in scope; the youth sees the current value and who set it | No | DPO | DPO | DPO |
| N7 | **Self-registration request**: name, contact, e-mail/phone verification state, officer decision, including rejected requests (D-083) | Let youth ask to join without an invitation | The applicant | Officers reviewing the queue. The applicant is never told whether a matching record exists. | No | DPO | DPO | DPO |
| N8 | **Review flag**: Needs Review / Reviewed, with trigger and reviewer (D-084) | Work queue for data changes | System and officers | Staff in scope | No | DPO | DPO | DPO |

## 2. Checklist (continues the numbering of `data-protection-review.md`)

| # | Question | Where to look | Done |
|---|---|---|---|
| 24 | For each row N1 to N8: lawful basis, notice wording, retention period. | Table above | |
| 25 | Disability is special-category data. May PI360 hold it at all? If yes, under what condition? | D-063, D-082 | |
| 26 | The Go Blue enrollment sheet already has a disability Yes/No column (38 Yes, 2,520 No, 141 blank; totals only). May it be imported, or must historical records stay "Not recorded"? | `documents/Go Blue Trainee Placement Data.xlsx`, column header only | |
| 27 | The same sheet has "Average Monthly Income", "National ID", and household and parent-health columns. None is loaded today. Confirm they stay out, or say which may be loaded (D-064 covers National ID). | same | |
| 28 | Salary: band or exact amount? Who may see it? | D-080 | |
| 29 | Trainer comments may contain opinions about a young person. Is a length limit, a guidance note for trainers, or a ban on free text needed? | D-074 | |
| 30 | Youth ratings of employers and exit comments: a small employer could guess who wrote them. Is "averages only, hidden below 5 ratings, never shown to employers" enough? | D-013, D-077 | |
| 31 | Self-registration: what consent text, and what age check (minors)? How long is a rejected request kept? | D-083, checklist item 3 | |
| 32 | Does the youth consent notice (version `2026-11-v1`) need a new version that covers N1 to N8? Every youth would then be asked again. | `CONSENT_TEXT` in `backend/apps/portal/services.py` | |
| 33 | Subject rights: may a youth see their own trainer assessments and the availability history? | policy | |
| 34 | Is a full data-protection impact assessment required for these additions under the Kenya Data Protection Act? | policy | |

## 3. Safeguards the developers will build regardless of the answers
- **Feature flags off by default** for self-registration, disability, salary and youth-visible ratings.
- **Permission per sensitive field:**
  - disability: `participants.view_disability`;
  - skills verification: `participants.verify`;
  - assessments: `ydm.assess`.
- **Out-of-scope records return "not found"**, as they do today.
- **Every create, change and verification is audited**, with actor and time. Sensitive values are not written into audit text.
- **Reports show totals only, with small-cell suppression** (`exports.small_cell`). No identifiable export without the existing grant.
- **No real youth data in development or tests.** The synthetic dataset is `backend/scripts/seed_capyei_demo.py`.

## 4. Known limits
- There is no automatic retention or deletion yet, for this data or the existing data.
- Consent text is English only.
- SMS verification needs a provider (D-016, open). Until then, e-mail only.
