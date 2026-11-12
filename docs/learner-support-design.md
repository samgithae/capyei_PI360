# Learner portal, Phase 3: support tickets and placement follow-ups (design only)

Status: **design for review. No code until the open questions below are answered.**

## 1. Why a separate phase

Phase 1 (dashboard, My opportunities) is read-only and built from referral data that already
exists. Phase 3 lets the learner *write* something that staff must act on, and records
sensitive reports. It needs its own access rules, retention and ownership, so it is designed first.

## 2. Two features

### 2.1 Support tickets (learner raises, staff resolve)
A learner can raise a ticket from the portal, linked (optionally) to one of their placements.

| Field | Notes |
|---|---|
| category | pick from a seeded reference list: pay, working conditions, transport or housing, training mismatch, workplace conduct, safety or harassment, other |
| description | free text, learner's own words |
| placement | optional link to the learner's own placement/referral |
| status | open, in progress, resolved, closed (history kept, append-only like stage events) |
| visibility | **normal** or **restricted** (see 3) |

Staff reply and change status; the learner sees status and replies addressed to them. Every
change is an append-only event plus an audit record (same pattern as `StageEvent`).

### 2.2 Placement follow-ups (staff check in, learner answers)
After a placement starts, the system schedules check-ins at **1 week, 30, 60, 90 days and
6 months** from the start date. Each is a short form: still in the job (yes / no, why), pay
received on time, any concern (opens a ticket), and a free comment. Staff can also record the
check-in by phone on the learner's behalf (source = staff). A missed check-in is flagged to the
owner, never to the employer.

## 3. Access rules (the important part)

1. Learner sees only their own tickets and follow-ups (same `youth.self_service` scoping as Phase 1).
2. **Employers never see tickets or follow-ups.** There is no employer login today; any future
   employer view must exclude these tables by design.
3. Category `safety or harassment`, or a learner ticking "keep this private", makes the ticket
   **restricted**: visible only to a named safeguarding role (new permission `support.restricted`)
   and the learner, **not** to the learner's usual placement officer or the data steward.
4. Staff scope applies to normal tickets exactly as it does to referrals (an officer sees tickets
   for youth in their caseload).
5. Audit records field names and ids only, never the ticket text (as `youth.details_edited` does).
6. Retention and DPO review: tickets hold sensitive data; the retention period must be agreed
   before pilot (same review as `docs/data-protection-review.md`).

## 4. Data model sketch (new module `apps/support`)
- `TicketCategory` (reference data, configuration pattern)
- `Ticket` (participant, placement nullable, category, restricted, status, created_at)
- `TicketEvent` (append-only: message / status change / assignment, actor, visible_to_learner)
- `FollowUpSchedule` generated when a placement gets a start date; `FollowUp` (due_date,
  milestone, status: due / done / missed, answers JSON, source: learner | staff)
Import-linter: `support` imports participants/placements/identity services only; portal
composes it, as it does for referrals.

## 5. Open questions (need an owner's answer)
1. **Who owns tickets and follow-ups?** The placement officer, a central support desk, or
   a safeguarding lead for restricted ones? This sets assignment and the new role.
2. Do check-ins by phone (staff-recorded) need to exist from day one, given limited data or
   smartphone access for many learners?
3. Can the learner mark a ticket resolved themselves, or only staff?
4. How are learners reminded (e-mail now; SMS later needs a provider and consent wording)?
5. Retention period for tickets and follow-up answers.
6. Where do placements get a reliable start date? Imported placements have `start_date`
   but the referral flow's "placed" step does not record one yet; follow-ups need it.

## 6. Suggested build order after approval
1. Placement start date on the placed step (small change in referrals).
2. Ticket reference data, tickets, restricted visibility and the safeguarding permission.
3. Follow-up schedule, learner form and staff phone-entry.
4. Staff views: a ticket queue and an overdue follow-up list (also feeds reports).
