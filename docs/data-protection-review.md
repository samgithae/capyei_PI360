# Data-protection review: youth sign-in and self-service

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
