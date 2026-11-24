# CAP-YEI dashboard metrics: proposed definitions (for B43 / D-089)

**PI360** · Planning document · 23 Nov 2026 · Status: **proposed, not approved**. D-089 is Open.

The decision pack asked CAP-YEI to approve the metrics in "plan section 5.13". That section does not exist; the reference was our mistake. This document replaces it. CAP-YEI can **approve, amend or defer** each metric.

Until a metric is approved, the dashboard still shows it, labelled "definition not yet approved" (the existing `approved` flag in `apps/reporting/services.py METRICS`, task NEW-062). All counts respect the viewer's scope. Archived and merged records are excluded, as for the existing metrics.

**Small numbers:** any total about disability, and any employer aggregate, is hidden below a minimum count. For employer aggregates that minimum is still to be set (A6, D-077).

| # | Metric | Definition | Calculation | Period | Source | Depends on |
|---|---|---|---|---|---|---|
| 1 | Skills awaiting review | Youth with at least one self-reported skill not yet verified | Count of distinct youth | As at today | Participant skills (source = youth, no verification) | B6–B8 |
| 2 | Skills reviewed and verified | Youth whose skills were verified, as Verified or Needs Reassessment | Count of distinct youth with a verification in the period, split by outcome | Chosen date range | Verification records | B7 |
| 3 | Youth assessed | Youth with at least one submitted competency assessment | Count of distinct youth | Chosen date range | Assessments | B13–B17 |
| 4 | Average assessment score | Mean of each youth's **latest** overall score (overall = average of the 6 competency averages; blanks excluded) | Sum ÷ number of assessed youth, 1 decimal; shown with "n youth" | Latest as at today | Assessments | B15 |
| 5 | Open for opportunities | Youth whose availability is Open | Count, and % of registered youth | As at today | Availability flag | B9–B12 |
| 6 | Employer ratings | Number of youth ratings of employers, and the share negative (1–2), neutral (3) and positive (4–5) | Counts and % | Chosen date range | Employer feedback (party = youth) | B20, B21 |
| 7 | Employers under review | Employers with an open alert (≥3 ratings averaging below 3.0, or any single 1) | Count, by outcome (Monitor / Ignore / not yet reviewed) | As at today | Employer reviews | B22, B23 |
| 8 | Changed employers | Youth whose placement ended with "changed employer" and who started a new placement with another employer | Count of distinct youth | Chosen date range | Placements (`previous` link) | B25, B28 |
| 9 | Moved to self-employment | Youth whose wage placement ended and who then recorded a self-employment outcome | Count of distinct youth | Chosen date range | Placements and follow-ups | B27 |
| 10a | Retained with the same employer (3 / 6 / 12 months) | Of youth placed at least N months ago, those still with the **same** employer N months after start | Retained ÷ eligible, for N = 3, 6, 12 | Cohort by placement start | Follow-ups | B26 |
| 10b | Retained in work with another employer (3 / 6 / 12 months) | Of the same eligible youth, those working for **another** employer (or self-employed, if CAP-YEI agrees) at N months | Retained ÷ eligible, for N = 3, 6, 12 | Cohort by placement start | Follow-ups | B26, B27 |
| 11 | Referral to interview | Referrals that reached the Interview stage | Interviewed ÷ referred | Referrals made in the date range | Referral stage events | — |
| 12 | Interview to placement | Interviewed referrals that reached Placed | Placed ÷ interviewed | Referrals made in the date range | Referral stage events | — |
| 13 | Employer responsiveness | Median days from referral to the employer's first response (any stage after Referred) | Median, with the count of referrals | Referrals made in the date range | Referral stage events | — |

**Questions for CAP-YEI with this list:**
1. For 10b, does self-employment count as "retained in work"? (We propose: shown separately, not counted.)
2. For 10a/10b, is a youth with no follow-up at N months left out of the count (our proposal) or counted as not retained?
3. For 13, what counts as the employer's first response? (We propose: the first stage change after Referred, made by anyone.)

Nothing here changes retention periods for stored data. "Retention" in this document means youth staying in work, not how long PI360 keeps records.
