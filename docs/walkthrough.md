# PI 360 walkthrough: youth → employer → opportunity → rules → referral

A hands-on guide to try the whole flow on your local copy. It follows the order work happens in real life, and says what the system does at each step and why.

> **Honest status:** the rules screens (write, review, approve, activate) are built, and the active Compatibility rule is now applied on screen: an opportunity shows **Suggested youth** (see step 6). Suggestions only help; *you* decide the referral and the system records what you decide. Support priority (Module A) and employer reliability (Module C) are not applied on screen yet. Youth can now be invited to sign in and add their own skills (step 8).

## 0. Before you start

- API on `http://localhost:8010`, web on `http://localhost:5174`.
- Dev logins are created by `backend/scripts/seed_dev.py` (usernames and passwords are at the top of that file). Roles you will use:

| Login | Role | What it is good for here |
|---|---|---|
| `dev.steward` | Data steward | create youth, employers, reference data |
| `dev.admin` | Administrator | write, approve and activate rules; manage roles and staff |
| `dev.officer` | Placement officer | refer youth and move referrals (only sees *their* caseload) |
| `dev.viewer` | Manager | oversee the officer's caseload |
| a youth you invite | Youth | sees and edits only their own skills (step 8); no seed login, created by invite |

**Why several roles?** Separation of duties. The person who creates data, the person who approves rules and the person who works referrals are different jobs, and each action is checked against the role.

## 1. Set up the reference lists (once)

**Where:** Administration menu.

Dropdowns everywhere come from these lists, so fill them first: **Programmes → Cohorts → Courses → Cohort courses**, **Training institutions**, **Sectors**, and the geography (**Counties → Sub-counties → Wards**).

- **Bulk load:** programmes, cohorts, courses, cohort courses, training institutions and sectors each have an **Import** button. Download the template, fill it in a spreadsheet, upload the .csv or .xlsx, **Preview** (nothing is saved), then confirm. Existing records are skipped, rows with errors are listed by row number and the rest still load. Import in this order: sectors, programmes, institutions, courses, cohorts, cohort courses (each file points to the earlier ones by code or name).
- Counties (47), sub-counties (290) and wards (1,448) load automatically when the database is migrated.
- Click a county to see its sub-counties; click a sub-county to see its wards.
- A cohort-course is "this cohort runs this course". A youth is enrolled into one of these.
- "Retire" hides an entry from new records but keeps it on old ones. Nothing is hard-deleted, so history stays truthful.

## 2. Create a youth

**Where:** Youth → **Add youth** (a four-step wizard). Log in as `dev.steward`.

1. **Identity.** Only the name is required. Add national ID, date of birth, gender, status when you have them. *Why optional:* real registers are incomplete; the system flags gaps rather than blocking you.
2. **Home and contact.** Phone, email, and the residence: County → Sub-county → Ward. Each list follows the one before it. Choosing a county first is what fills the sub-county list.
3. **Enrollment.** Pick a Cohort, then a Course (only courses that cohort runs), and the enrollment status.
4. **Review.** Check and save.

What happens behind the scenes:
- The system checks for a likely duplicate (same ID or very similar name and details) so one person does not become two records. Duplicates go to **Duplicates** for a person to merge or dismiss.
- Every change is written to an audit trail: who, what, when.
- Changing the residence later *closes the old address and keeps it in the history*, so you can always see where someone lived at a given time.

**Check it:** Youth list → open the new person. You should see enrollments, contacts, residence and history.

## 2b. Add the youth's skills and readiness (capability profile)

**Where:** open a youth → **Skills and readiness** card → **Edit**. Log in as `dev.steward`.

The profile has four parts: **qualifications** (highest level and field), **skills** (from the Skills list, with a proficiency), **work experience** (sector and months) and **availability** (start date, work patterns, sectors of interest). Fill only what you know; empty means "missing", never "failed".

- Each entry shows its **source** (staff, import or self-reported) and whether it is **Verified**. Use **Verify** after checking evidence. Editing an entry removes its verification.
- **Bulk load:** Youth → **Import** takes a CSV/Excel file with one fact per row, matched by enrollment number. Imported facts are marked *import* and unverified. Download the template, **Preview**, then confirm. Rows that fail are listed by row number.
- Skills and qualification levels come from Administration lists (Skills, Qualification levels); the starter values are proposals until the product owner confirms them.
- Not built: capability fields in the **Add youth** wizard. Add them afterwards on the profile.

**Check it:** the card shows what you saved, with source and verified badges.

## 3. Create an employer

**Where:** Employers → **Add employer**.

Fields: name, sector, county, sub-county, address, website, status (active / inactive / prospect), notes.

- On save, the system looks for **similar names** ("Safaricom Ltd" vs "Safaricom Limited"). You can "Save anyway" if it really is a different employer.
- Status matters: an opportunity can only be **opened** for an *active* employer.
- Need a sector that is missing? Use the "Add or manage sectors" link under the dropdowns.

## 4. Create an opportunity (and its requirements)

**Where:** Opportunities → **Add opportunity**, then open it.

1. **Create:** choose the employer, title, type (job, training, attachment), number of positions, closing date. It saves as a **Draft**.
2. **Add requirements** (on the opportunity page). Each has a category (skill, qualification, experience, availability, location, other) and marked **mandatory** or **preferred**.
   - *Mandatory* = if the youth lacks it they may be "not eligible".
   - *Preferred* = only adds to a fit score.
   - These are what the compatibility rule (Module B) will read later.
3. **Open it.** Needs a closing date and an active employer. Only an **open** opportunity, on or before its closing date, can receive referrals.
4. **Lifecycle:** Draft → Open → Closed / Expired. The day after the closing date a daily job marks it Expired (and referrals are blocked even before the job runs). Closed and Expired are *locked*: no edits until you **Reopen**. *Why:* so the record of what was offered cannot be rewritten after referrals were made against it.

Skill, qualification, experience and availability requirements take a **structured value** (pick the skill or minimum qualification from the lists, enter months, or a start-by date and work pattern). The wording is written for you if you leave it empty. Older free-text requirements show a **Needs structuring** badge until someone edits them; the rules cannot check those. Location and other stay as plain text.

## 5. Rules: write, review, approve, activate

**Where:** Rules menu. Log in as `dev.admin` (the Administrator can both draft and approve).

There are three **rule sets**, one per question the system helps answer:

| Module | Question | Output |
|---|---|---|
| A. Support priority | Who may need extra follow-up? | A flag with a reason, in a staff queue. Never blocks access to opportunities. |
| B. Compatibility | How well does this youth fit this opportunity? | Mandatory checks → eligible / eligible with unknowns / not eligible; preferred factors → a score. |
| C. Employer reliability | How has this employer responded in the past? | Indicators (response rate, interview and placement conversion, early retention), hidden as "insufficient evidence" when there are too few records. |

A rule set has numbered **versions**. A version is a list of **factors** (the checks, e.g. "months of experience is at least the requirement") and **parameters** (the numbers they use, e.g. "how many days is too long").

Walk one version through its life:

1. Open a rule set, then a version. Only a **Draft** can be edited.
2. In a draft, click **Edit draft** to open a four-step wizard (no JSON needed):
   - **Checks:** switch each check on or off and rename it. Whether a requirement is mandatory or preferred is set on each opportunity, not here.
   - **Numbers:** give each check points (the share of the total is shown) and set the limits. Tick **Confirmed by the product owner** only when they have actually confirmed it.
   - **Missing information:** choose, per check, whether a missing value flags the youth for staff review or leaves that check out. It is never counted as a failure.
   - **Review:** read the summary, add notes, and **Save draft**. Nothing is saved until this step.

   Developers can still use **Advanced: edit as JSON** from the wizard.
3. **Send for review.** (Rule author action.)
4. **Approve.** Refused while any parameter is still undecided. *Why:* an unconfirmed threshold must never reach production.
5. **Activate.** The new version goes into force and the one it replaces is **Retired**.
6. To change anything later: **Copy as new draft** from the active version, edit the copy, repeat. The version in force is never edited, and every step records who and when. A reviewer can **Return to draft** with a note saying what to change.

Why so strict: the rules decide who gets support and who is called a good fit. People must be able to see exactly which version was in force when a suggestion was made, and who approved it.

**Check it:** the version page shows status, "what changed", created-by, and a history of every step.

## 6. Refer a youth to the opportunity

**Where:** open the opportunity → **Refer youth** (or Referrals → add). Log in as `dev.officer`.

An officer sees only youth in their **caseload**; anyone else looks like they do not exist. That is by design.

1. Search for the youth, choose them, then **Send referral** (or **Save draft** to hold it back).
2. Use the **Suggested youth** panel on the opportunity page as a guide. It groups the youth you can see as *eligible*, *eligible with unknowns* or *not eligible*, with a fit score and what is missing from each record. Youth with no capability details are counted but not ranked, and missing information never counts against anyone. The *decision is yours*; nothing is referred automatically.
   - The panel reads each youth's qualification, skills, experience and availability. Add them on the youth's profile, or in bulk with **Youth → Import** (one row per fact, matched by enrollment number; imported facts are marked *import* and unverified until staff verify them).
   - Location is not checked yet.
3. The referral then moves through stages. Every move adds a row to its history and nothing is overwritten:

```
Draft → Submitted → Under review → Interview (optional) → Selected → Placed → Closed
              ↘ Rejected / Withdrawn / No response → Closed
```

4. Ending unsuccessfully (Rejected, Withdrawn, No response) **requires a reason code** from a fixed list, for example "skills gap", "distance or transport cost", "employer did not respond". *Why:* so the pilot can later learn why placements fail instead of reading free text. "Other" needs a written note.
5. **One live referral per youth per opportunity**, so there are no accidental duplicates.
6. Made a mistake? You cannot edit history. You add a **correction** with a written note pointing at the entry it fixes. The original stays visible. Reopening a closed referral needs a **Manager**.

**Check it:** Referrals list → open it → the history shows each move with who and when. Log in as `dev.viewer` (Manager) to see the same record from the supervising side.

## 7. What to try as a full dry run (phases 1 and 2 together)

1. Steward: add reference data (or import it from CSV), then add a youth in Nairobi → Westlands → Kitisuru, enrolled in a cohort, **with an e-mail address**.
2. Steward: on the youth, **Edit** skills and readiness: a qualification, one or two skills, some experience, an availability date. Click **Verify** on one entry.
3. Steward: add an active employer; add an opportunity with two mandatory and one preferred **structured** requirement (pick a skill, a minimum qualification, months of experience); open it.
4. Admin: open the Compatibility rule set, copy the active version, use **Edit draft**, confirm the numbers, send for review, approve, activate.
5. Officer: open the opportunity and read **Suggested youth**; refer the youth and move it Submitted → Interview → Selected → Placed → Closed.
6. Officer: refer a second youth and end it as Rejected. Notice the reason code is compulsory.
7. Steward: on the first youth, **Send invite** (step 8). Read the link from the API log, set a password, sign in as the youth, agree to the notice, add a skill.
8. Steward: reopen that youth and see the new entry marked self-reported; verify it. Then check **Suggested youth** again: the new skill is now counted.
9. Admin: open a rule version's history and a youth's history to see the audit trail, including the invite and the youth's own edits.

## 8. Youth sign-in and self-service (Phase 2)

**Staff side:** open a youth → **Youth sign-in** card (needs the *invite* permission and access to contact details). Choose one of the e-mail addresses already on the record and **Send invite**. There is no open registration: an account exists only because staff invited an address on the record. The link works once and expires in 7 days; **Send a new invite** replaces it and **Withdraw invite** cancels it.

**Youth side:** the e-mailed link opens a page to choose a password, then the youth signs in with that e-mail address. Their only page is **My profile**. It first shows a consent notice; after they agree they can see and edit their own qualifications, skills, experience and availability. Their entries are marked self-reported and unverified until staff verify them. They never see who verified an entry, cannot delete an entry staff have verified, and cannot see any other youth.

In local development the invite e-mail is printed in the API server's log (the link uses `FRONTEND_URL`, default port 5173; if your web server runs on 5174, replace the port in the link, or start the API with `FRONTEND_URL=http://localhost:5174`).

**Check it:** invite a youth with an e-mail on file, read the link from the API log, set a password, sign in, agree, add a skill, then open the youth as staff and see it marked self-reported.

Before real youth are invited, a person responsible for data protection must work through `docs/data-protection-review.md`.

## 9. What is not built yet

- Support-priority flags and employer reliability profiles on screen (Month 3). Compatibility is applied (Suggested youth).
- Support cases / work queues (Month 3).
- Capability fields in the Add youth wizard; location is not checked in Suggested youth.
- Rule weights and thresholds are placeholders until the product owner confirms them.
- Youth: no withdraw-consent button, no forgotten-password screen (staff re-invite), no second factor, English-only consent text. A human data-protection review (`docs/data-protection-review.md`) is still outstanding.
- Placement follow-up at 30 and 90 days: shown in the pilot guide diagram, not checked by me whether it is wired up.
