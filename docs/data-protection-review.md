# Data-protection review: youth sign-in, self-service and the employer portal

Status: **not reviewed.** This is a checklist for a person (the organisation's data-protection officer or equivalent) to work through before any real youth are invited. Nothing here is legal advice, and the developers cannot sign it off.

Reviewer: ____________  Date: ____________  Outcome: approve / approve with changes / reject

## What the feature does
- Staff with the invite permission send a one-time link to an e-mail address already on a youth's record.
- The youth sets a password, signs in, and sees only their own record: qualifications, skills, work experience, availability.
- They must accept a consent notice (version `2026-11-v1`) before the profile shows. A new notice version asks again.
- Their entries are stored as self-reported and unverified until staff verify them.

## Checklist (reviewer ticks and notes)

| # | Question | Where to look | Done |
|---|---|---|---|
| 1 | Is the consent wording clear, in plain language, in the languages the youth use (English only today)? Does it match your lawful basis for processing? | `CONSENT_TEXT` in `backend/apps/portal/services.py` | |
| 2 | Is consent separate from sign-in, withdrawable, and what happens to data on withdrawal? (Today there is no withdraw button: the youth must ask an officer.) | portal services | |
| 3 | Are minors possible in the cohort? If so, is parental or guardian consent needed? (The system does not check age.) | policy | |
| 4 | Data minimisation: is each profile field needed for placement matching? | profile fields | |
| 5 | Retention: how long do inactive youth accounts and self-reported entries stay? (No automatic deletion exists.) | policy | |
| 6 | Access: a youth sees only their own record; staff see only their scope. Confirm with a test account. | `tests/test_youth_portal.py`, `tests/test_authz_matrix.py` | |
| 7 | Invite security: random token, only its hash stored, 7-day expiry, single use, sent only to an address on file, link carries the token in the URL fragment. Is this acceptable? | `backend/apps/portal/services.py` | |
| 8 | Authentication: youth accounts use a password only (no second factor). Is that acceptable for this data, or should e-mail or SMS codes be added? | `backend/apps/identity/mfa.py` | |
| 9 | Audit: invites, activation, consent and profile changes are recorded with actor and time. Confirm the audit trail is reviewed by someone. | audit module | |
| 10 | E-mail delivery: which provider sends the invite, where is it hosted, and is a data-processing agreement in place? | production settings | |
| 11 | Subject rights: how does a youth request access, correction or deletion, and who answers? | policy | |
| 12 | Breach response: who is told, and how fast, if an account is compromised? | policy | |
| 13 | Does any regulator registration or impact assessment apply (for example under the Kenya Data Protection Act)? | policy | |

## Known limits (from the developers)
- No withdraw-consent button, no self-service deletion, no automatic retention.
- No second factor for youth accounts.
- Consent text is English only.
- A youth cannot reset a forgotten password by themselves yet; staff must send a new invite.

---

# Addendum: the employer portal

Status: **not reviewed.** Same rules as above: a person must work through this before any real employer user is invited.

## What the feature does
- PI staff (and later the company's own admin) invite people at a company by e-mail. Each gets a one-time link, sets a password, and signs in like a youth.
- One person belongs to one company. A company admin gives each colleague one of four fixed roles: Company admin, HR / Recruiter, Hiring manager, Employer viewer.
- Employer users see only their own company: its profile, opportunities and the referrals made to it, plus a dashboard of counts, charts and recent activity.
- A referred young person's profile and CV are visible to the company. Their phone number and e-mail appear **only once the company has selected them**.
- Employers can reply to a referral (under review, interview, selected, rejected with a reason) and set an interview. Only PI staff mark someone Placed or Closed.
- Opportunities an employer submits wait for PI staff approval unless the `employer_self_publish` switch is on (off by default). A second sign-in step can be required with `employer_mfa_required` (off by default).

## Checklist

| # | Question | Where to look | Done |
|---|---|---|---|
| 14 | Is it right that an employer sees a referred youth's full profile and CV before selecting them? What is the lawful basis, and is it in the youth's consent notice (which today does not mention employers)? | `backend/apps/referrals/own.py`, `CONSENT_TEXT` | |
| 15 | Is hiding phone and e-mail until selection the right line? Should the youth be told when their contact details are shared? | `contact_visible` in `own.py` | |
| 16 | Isolation: an employer user can never read another company's data or any staff note, score or compatibility detail. Confirm with test accounts for two companies. | `tests/test_employer_data.py`, `tests/test_employer_dashboard.py`, `tests/test_authz_matrix.py` | |
| 17 | Who may create a company's first account, and how is the person verified as belonging to that company? (Today: PI staff with `employers.invite_user`, by judgement.) | policy | |
| 18 | Invite security: random token, only its hash stored, 7-day expiry, single use, link carries the token in the URL fragment. Acceptable? | `backend/apps/employer_portal/services.py` | |
| 19 | Authentication: employer users use a password only unless the MFA switch is on. Should it be on, at least for Company admin? | `employer_mfa_required` | |
| 20 | Leavers: a company admin can suspend a colleague. Who tells PI staff when the company admin leaves? Is a company always left with one admin (the system enforces this)? | policy | |
| 21 | Audit: invites, role changes, suspensions, publish requests and referral replies are recorded with actor and time. Is the trail reviewed? | audit module | |
| 22 | The employer-visible CV download is logged. Is that enough, or should downloads be limited? | `own_cv_pdf` | |
| 23 | Retention: how long do employer accounts and their replies stay after a company leaves the programme? (No automatic deletion.) | policy | |

## Known limits (from the developers)
- The youth consent notice does not yet say employers see profiles and CVs of referred youth. Update it before any pilot.
- No employer-side data export or deletion request flow.
- Employers cannot reset a forgotten password by themselves; staff or the company admin send a new invite.
- Interview dates are shown to the company only; the youth is not notified by the system.
