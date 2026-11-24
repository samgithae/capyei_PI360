# CAP-YEI decision pack: changes asked for at the 23 November 2026 meeting

**For:** CAP-YEI placement lead, programme lead, training lead, M&E lead, sponsor and the data-protection officer (DPO).
**From:** PI360 developers.
**Status (updated 23 Nov 2026):** **answered.** CAP-YEI and the DPO's consolidated answers were received on 23 Nov 2026 and are recorded in `planning/registers/decisions.csv` and `docs/capyei-decision-register.md` §0. The questions below are kept as they were sent. Still open: B16 approval step, B17 interval, B18 weight, B19 criteria, B30 position, B43 metrics (now defined in `docs/capyei-metric-definitions.md`; the "section 5.13" reference below was wrong), A6 minimum count and A2 (DPO confirmation). Our follow-up questions C-1 to C-6 are in `docs/capyei-answers-impact-assessment.md` §7.

*Original status when sent:* every decision below is **open**. Nothing has been built on an assumed answer. Where we give a recommendation it is only a suggestion; you decide.
**Detail behind each question:** `docs/capyei-decision-register.md` (options, consequences, tasks blocked). Register rows: `planning/registers/decisions.csv`, D-070 to D-090.
**Privacy questions:** `docs/capyei-dpia-addendum.md` (for the DPO).

How to answer: for each question, write the option letter (or your own answer), your name and the date. A decision is recorded as "Decided" only when we receive that written answer.

---

## Part A. Questions for the DPO first (they gate everything else)

These features can be built and tested on made-up data, but they stay switched off for real youth until the DPO answers.

| # | Question | Decision |
|---|---|---|
| A1 | May PI360 hold **disability** information at all? Note: the Go Blue enrollment sheet already has an "I have Disability" column (Yes 38, No 2,520, blank 141). Today PI360 does not load it. If allowed, may these historical answers be imported, or must they stay "Not recorded"? | D-082, D-063 |
| A2 | For each new kind of data (trainer assessments, employer ratings by youth, exit comments, disability, salary band, self-registration requests including rejected ones): what is the **lawful basis**, what **notice wording** must the youth see, and how long may it be **kept**? | D-090 |
| A3 | May **salary** be recorded at follow-up? If so, as a band or an exact amount? Note: the Go Blue sheet already holds "Average Monthly Income" at enrollment, not loaded today. | D-080 |
| A4 | Exit feedback: may youth submit it in the portal, may officers record it for them, and is it confidential from the employer? | D-079 |
| A5 | Self-registration: may youth sign up without an invitation, and what consent text must they accept? Is a rejected sign-up kept, and for how long? | D-083 |
| A6 | Employer ratings: may an employer ever see an aggregate of the ratings youth gave them? (We suggest not in the pilot, because a small employer could guess who rated them.) | D-077 |

## Part B. Questions for CAP-YEI

### Projects, courses and cohorts

| # | Question | Our suggestion | Ref |
|---|---|---|---|
| B1 | Should "Programme" become "Project" only on screens, reports and templates, or must the database and API be renamed too? | Screens only. | D-070 |
| B2 | Should courses be one shared list, offered by cohorts in any project, instead of belonging to one project? | Yes, a shared list. | D-071 |
| B3 | **Confirmed 23 Nov 2026 by the PI360 side: the meeting's "GoBrew" means Go Blue.** Please send a made-up or redacted example of the spreadsheet you set up a new project from. See Part C. | — | D-071 |
| B4 | In Go Blue, a cohort label holds the centre, intake year, batch, phase and year of study, for example "X VTC - 2024 Batch 1-Phase 1-Year 1". Is that one cohort, or should phase and year of study be tracked separately? | Keep one cohort per label for now. | D-071 |
| B5 | Please confirm the course codes 001 to 007 taken from the Go Blue file. Is course 006 (SIYB, one trainee) a real course? | — | D-071, D-062 |

### Skills verification

| # | Question | Our suggestion | Ref |
|---|---|---|---|
| B6 | Who may verify skills for many youth at once? | Placement and Project officers, with a new "verify skills" permission. | D-072 |
| B7 | Which outcomes may be applied in bulk: Verified, Needs reassessment, Rejected? | Verified and Needs reassessment only; Rejected one at a time with a reason. | D-072 |
| B8 | Is one method and one note enough for a whole batch? | Yes. | D-072 |

### Open for Opportunities

| # | Question | Our suggestion | Ref |
|---|---|---|---|
| B9 | What should the flag default to for youth who are never placed, placed, exited, or self-employed? | Open, except currently placed youth, who default to closed. | D-073 |
| B10 | Who may change it: the youth, the officer, or both? Can an officer override the youth's own choice? | Both; an officer override needs a reason, and the youth sees who set it. | D-073 |
| B11 | Should the flag expire and need reconfirming? After how many days? | No expiry in the pilot; report flags older than a number of days you choose. | D-073 |
| B12 | Should youth who are not open be left out of suggestions, or only ranked lower? What happens to referrals already made? | Left out; existing referrals stay active, and the officer is warned. | D-073 |

### Trainer competency assessments

| # | Question | Our suggestion | Ref |
|---|---|---|---|
| B13 | Are the six competencies (Time management, Communication, Interpersonal skills, Maturity, Leadership, Personality/attitude) the same instrument as the IYLDP/YDM template? | Yes, treat them as one instrument. | D-074 |
| B14 | Please confirm in writing that YDM/IYLDP assessment is in pilot scope. | — | D-065 |
| B15 | What is the rating scale, and what does each point mean? How are category scores and an overall score worked out, and what if a criterion is left blank? | You decide; scores are hidden until this is set. | D-052 to D-055 |
| B16 | Who records assessments: trainers, development officers, or both? Does anyone need to approve them? | Either may record; no approval; a correction is a new assessment that keeps the old one. | D-075 |
| B17 | How often is a youth reassessed? | On demand; an optional reminder interval you set. | D-075 |
| B18 | Should assessments affect matching? If so, as a preferred factor with what weight, and what happens to youth with no assessment? | Display only until B13 to B15 are settled, then a preferred factor. "No assessment" never counts against a youth. Never a hard requirement. | D-076 |

### Employer ratings and alerts

| # | Question | Our suggestion | Ref |
|---|---|---|---|
| B19 | Are the five criteria final: work environment, management and supervision, treatment and respect, working conditions, overall experience? | — | D-077 |
| B20 | Is the scale 1 to 5? What does each point mean? | — | D-077 |
| B21 | What counts as a negative rating, for example any criterion at 2 or below? | You set the number. | D-078 |
| B22 | How many negative ratings within how many days should open an administrative review? | You set the numbers; no alert fires until you do. | D-078 |
| B23 | What review outcomes do you want? | No action, monitor, discuss with employer, pause new referrals (manual, with a reason). No automatic suspension. | D-078 |
| B24 | Should employer evidence change the order of suggested opportunities? | A separate "employer evidence" column and sort, not a combined score. | D-087 |

### Follow-ups and placements

| # | Question | Our suggestion | Ref |
|---|---|---|---|
| B25 | What are the lists for employment type and reasons for leaving? | — | D-080 |
| B26 | Does "retained" mean with the same employer, or in any job? | Report both. | D-080 |
| B27 | Does self-employment count as a placement outcome? | Its own outcome, counted as "in employment". | D-080 |
| B28 | Can a youth have two running placements at once? | Yes; "changed employer" ends the old one unless the officer keeps both. | D-081 |
| B29 | Is the Go Blue placement sheet the full history, or only the latest placement? | — | D-066 |

### Disability field

| # | Question | Our suggestion | Ref |
|---|---|---|---|
| B30 | The action item says "after **Jeddah**", and the discussion said after **Gender**. There is no "Jeddah" field. Did you mean Gender? | Right after Gender. | D-082 |
| B31 | Exact wording and answers? | "Do you have a disability?" Yes / No / Prefer not to say, plus "Not recorded". | D-082 |
| B32 | Who may see it? | Only roles given a special permission; reports show totals only, hiding small numbers. | D-082 |

### Self-registration and review status

| # | Question | Our suggestion | Ref |
|---|---|---|---|
| B33 | How are sign-ups verified: e-mail, phone, or both? Phone needs an SMS provider (D-016, open). | E-mail now; phone when SMS exists. | D-083 |
| B34 | Must an officer approve every sign-up before an account works? | Yes: the officer links it to an existing record, creates a new one, or rejects it. | D-083 |
| B35 | What makes a youth "Needs Review"? Please confirm the list: new self-registration, youth edited key fields, import changed key fields, officer flagged with a reason. | — | D-084 |
| B36 | Who may mark a youth "Reviewed"? Should "Needs Review" stop anything? | Any officer in scope; it stops nothing and is a work list only. | D-084 |

### Project Officers and access

| # | Question | Our suggestion | Ref |
|---|---|---|---|
| B37 | Should a Project Officer have the same rights as a Placement officer, limited to their projects? | Yes. | D-085 |
| B38 | A youth enrolled in two projects: visible to officers of both? | Yes. | D-085 |
| B39 | Youth with no project: who sees them? | Only all-scope roles; the data steward gets a list to fix. | D-085 |
| B40 | May Project Officers export identifiable data, or import? | No identifiable export unless granted per person; imports only for their projects. | D-085 |
| B41 | Should employers and opportunities stay shared across projects? | Shared for the pilot. | D-086 |
| B42 | Should youth see "suitable opportunities" in the portal, or only ones an officer referred them to? | Referred only, until D-006 and D-007 are decided. | D-088 |

### Dashboard

| # | Question | Our suggestion | Ref |
|---|---|---|---|
| B43 | Do you approve the new metric definitions in plan section 5.13? You can approve, amend or defer each one. Unapproved metrics still show, labelled "definition not yet approved". | — | D-089 |

---

## Part C. The Go Blue setup problem: what we found (read-only)

**What we did:**
- Searched the code, the planning documents and the documents folder.
- Read **column headers only** from `documents/Go Blue Trainee Placement Data.xlsx`.
- Counted course labels and centres, plus Yes/No totals for one column.
- No youth names, numbers or other personal values were read out or copied.

**Findings:**
1. **"GoBrew" in the meeting notes is Go Blue** (a transcription error, confirmed 23 Nov 2026). The source is `documents/Go Blue Trainee Placement Data.xlsx`.
2. **Go Blue's shape:**
   - one programme (Go Blue);
   - 9 training centres ("VTC Name");
   - 36 cohorts, each one label made of centre + intake year + batch + phase + year of study;
   - 7 courses, numbered 001 to 007 **across the whole programme, not per centre**;
   - 73 cohort-course offerings.
   - The file carries no codes; the codes we use are our proposals (dry run, 11 Nov 2026, `planning/17_Data_Quality_and_Migration_Report.md` §7).
3. **Why the setup is awkward in PI360 today:**
   - A course must belong to one programme (`Course.programme` is required, and codes are unique per programme).
   - Go Blue treats courses as one shared list offered by many cohorts.
   - If a second project offers the same course (for example Hospitality), it has to be created again under that project, and nothing links the two copies.
   - The cohort label packs five facts into one text, so setting up a new intake means building that exact label.
   - This matches the meeting's request that courses be independent. *(The link between the request and this cause is our inference.)*
4. **Also in the file:**
   - The Enrollment sheet holds sensitive columns PI360 does not load today: "I have Disability", "Average Monthly Income", "National ID", household and parent-health columns.
   - These are DPO questions (A1, A3; D-063, D-064). We did not load or copy any of them.

**What is still needed from CAP-YEI:**
- Send a **made-up or redacted** sample of the sheet you use to set up a new project.
- Answer B2, B4 and B5.

The course-code clash check (any two projects using the same course code for different courses) will be run read-only on the shared database once that database is agreed (D-035); it reports codes and counts only.
