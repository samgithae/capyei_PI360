# PI 360 walkthrough: full test (pilot dry run)

One pass through every part of the app, in the order work happens. About 90 minutes. Use the
persistent dev stack (web http://localhost:5174, API 8010, Postgres). Use synthetic data only.

Written 2026-11-23 from the project's build log. It replaces the earlier walkthrough, which stopped
before placements, follow-ups, cases, reports, exports and data quality. It has not been run end to
end as a script; if a step does not behave as written, note the step number.

Roles: sign in with your own admin account, and use the seeded `dev.*` logins (usernames and
passwords are at the top of `backend/scripts/seed_dev.py`) for the role checks. Do not share passwords in chat.

| Login | Role | Used for |
|---|---|---|
| your account | Administrator | settings, rules, access grants, retention |
| `dev.steward` | Data steward | youth, employers, data quality, imports |
| `dev.officer` | Placement officer | referrals, placements, follow-ups (own caseload only) |
| `dev.viewer` | Manager | oversight, reopening |
| M&E analyst (create one) | M&E analyst | reports only, no records |

## Part 1. Set up (Administrator) — 10 min
1. **Administration > Programmes, Cohorts, Courses, Cohort courses, Institutions, Sectors.** Add one of each, or use the **Import** button (download template, Preview, confirm). *Expect:* Preview saves nothing; error rows are listed by row number.
2. **Administration > Youth records.** Switch on consent tracking. *Expect:* a consent card and a "No consent" badge now appear on youth.
3. **Administration > Follow-up schedule.** Check the defaults: 30 d, 90 d, 6, 12, 24 months.

## Part 2. Youth (Data steward) — 15 min
4. **Youth > Add youth.** Enter "Grace Atieno": county > sub-county > ward, a phone, an e-mail, cohort and course. *Expect:* each geography list follows the one before it.
5. Add "Grace Atieno" again. *Expect:* a duplicate warning at the name step and again at Review (it never shows the phone or birth date).
6. Open the youth. Edit **Skills and readiness** (qualification, two skills, experience, availability) and **Verify** one entry. Set **consent** to Given.
7. **Youth > Import**: upload a small file of skills (one fact per row, matched by enrollment number). *Expect:* imported facts show "import", unverified.
8. **Duplicates**: merge or dismiss the seeded "Grace Akinyi" pair. **Data quality**: open a rule (e.g. no county), fix one youth. *Expect:* the fix is kept as a correction (was, now, who, when); export corrections.
9. **Imports**: upload a messy sheet. *Expect:* validation, match review, a reconciliation report; re-uploading the same file shows differences, not duplicates.

## Part 3. Employers and opportunities (Data steward) — 10 min
10. **Employers > Add employer** "Safaricom Ltd", then "Safaricom Limited". *Expect:* a similar-name warning; Save anyway works.
11. **Opportunities > Add.** Create a job with two mandatory and one preferred structured requirement (pick a skill, minimum qualification, months). Open it. *Expect:* opening needs a closing date and an active employer.
12. Close it, then reopen. *Expect:* closed/expired opportunities are locked until reopened.

## Part 4. Rules (Administrator) — 10 min
13. **Rules > Compatibility.** Copy the active version, **Edit draft** (four steps), set numbers, Send for review, Approve, Activate. *Expect:* approve is refused while any number is undecided; the old version becomes Retired; history shows who and when.
14. **Rules > Settings** (Support priority and Employer reliability). Change a number. *Expect:* the change is audited.

## Part 5. Referral to placement (Placement officer) — 15 min
15. Open the opportunity, read **Suggested youth**. *Expect:* groups eligible / with unknowns / not eligible, with what is missing.
16. Refer the youth; move Submitted > Under review > Interview > Selected > Placed. Refer a second youth and end it Rejected. *Expect:* a reason code is compulsory; one live referral per youth per opportunity; history is append-only; a correction needs a written note.
17. On the Selected referral click **Record placement**. *Expect:* the form is pre-filled; enter a start date and save. Record the same placement again. *Expect:* a duplicate warning with "record anyway".
18. **Placements**: verify the placement. **Follow-ups**: *Expect:* check-ins created (30 d, 90 d ...); log an attempt, a response and a "still employed" answer.
19. Sign in as `dev.officer` and look for a youth outside their caseload. *Expect:* it does not exist for them.

## Part 6. Cases and support priority (Officer, Manager) — 10 min
20. **Support priority** shows unsuccessful or stalled referrals and ready-but-never-referred youth. Click **Mark reviewed**. *Expect:* the flag pauses.
21. **Cases**: create an intervention with an owner and due date; add a note; close it. *Expect:* an activity timeline; overdue items are highlighted.
22. Employer page: log **employer feedback** (1 to 5, with a source). *Expect:* the evidence card shows "Insufficient evidence" until the minimums are reached; retention is counted only from completed check-ins.

## Part 7. Insight (Administrator, M&E analyst) — 15 min
23. **Overview**: click a tile. *Expect:* it opens the exact list of records it counts.
24. **Reports**: open each of the five (Programme scorecard, Placement outcomes, Equity and reach, Retention, Employer and pipeline). On each, change filters (the County, Cohort and Period selects are searchable); read the "How these numbers are worked out" section. *Expect:* numbers change; many tiles show "n/a" or 0 because dev data is sparse.
25. **Export** PDF and Excel from a report. *Not yet clicked through in the UI*, so tell me what the files look like. *Expect:* Excel has Summary, one sheet per table, Definitions.
26. Sign in as the M&E analyst. *Expect:* reports open, but no youth records.
27. **Youth > Export**: *Expect:* needs a grant and a stated purpose. Grant yourself `exports.identifiable` under **Administration > Access grants**, tick or untick fields, download.

## Part 8. Portals (optional) — 10 min
28. On a youth, **Send invite** (read the link from the API log; change the port to 5174 if needed). Sign in as the youth. *Expect:* consent notice first, then My profile, My opportunities, My placement; no scores or staff notes.
29. **Administration > Employer portal**: invite an employer contact and check the employer's own dashboard, opportunities and referrals.

## Part 9. Safety and housekeeping — 5 min
30. **Administration > Data retention**: *Expect:* dry run by default, nothing is cleared, no period approved (production is blocked until the data protection decision).
31. **Help centre**: open "Reading and exporting the reports" and one more guide.
32. Check the audit trail on a rule version and a youth. Switch to dark mode and a narrow window on two pages.

## What to write down
For every step: pass / fail / confusing wording. Group findings as bug, wording, or missing feature.

## Known gaps (not bugs)
- No disability data; retention figures need real check-ins; definitions are marked "working".
- Rule weights and thresholds are placeholders until CAP-YEI approves them.
- YDM is not built. The MIS adapter is not built. Production import is blocked by the data protection decision.
- The DEBUG-only MFA bypass is still in the code (remove before go-live).
