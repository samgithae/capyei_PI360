# Employer portal: implementation plan

Status: **proposal, nothing built.** Written 2026-11-16 for review before any code.

## 1. What is being asked

Let people who work for an employer sign in to the platform, the way youth already can, so they can
manage:

1. **their company profile** (name, sectors, counties, address, contacts),
2. **their opportunities** (create, edit, open, close, set requirements),
3. **their referrals** (see who was suggested, why, the CV, and respond: review, interview, select, reject).

Plus:

- One employer can have **several users** (director, HR, recruiter ...), each with their own login.
- A way to **manage those staff accounts and what each role may do**.
- A **dashboard** with the key statistics, analytics and recent activity, where every figure is a
  **clickable action** that opens exactly the records it counts.

"Employee" in the request is read as "a person working for an employer company". The brief ended
with an empty fourth bullet ("-"); see open question Q1.

## 2. What already exists that we build on

| Need | Existing piece | How we reuse it |
|---|---|---|
| Accounts, roles, permissions | `identity`: `Role` (permissions JSON from the code catalogue), `RoleAssignment`, `create_pending_account`, `activate_account`, `suspend_user`, `set_roles`, lockout, session policy | Employer roles are ordinary `Role` rows with new permission codes |
| Invite and activate by one-time link | `portal`: `YouthAccount`, `YouthInvite` (hashed token, expiry), `send_invite`, `check_invite`, `activate` | Same mechanism, new `EmployerInvite` |
| Self-service pattern | one permission (`youth.self_service`), every view resolves "my own record" from the user | Every employer view resolves "my employer" from the membership |
| Employer data | `employers`: `Employer`, `EmployerContact`, `Opportunity`, `OpportunityRequirement`, services `update_employer`, `create_opportunity`, `transition`, `save_requirement` | Employer portal calls these services; no second copy of the rules |
| Referrals and stage rules | `referrals`: `Referral.TRANSITIONS`, `transition`, `set_interview`, reasons, `StageEvent` (append-only), `employer_counts` | Employer actions go through the same `transition`, so the audit trail and rules are identical |
| Safe candidate view | employer-safe CV and PDF (`build_cv`, `cv_pdf`), "Why suggested" (`referral_fit`), candidate cards on the referral page | Re-exposed through employer-scoped endpoints with a stricter field set |
| Dashboard pattern | `reporting` dashboard + drilldown; the overview page's "click the number to see the records" convention | Same shape, scoped to one employer |
| Tests and guardrails | `test_authz_matrix.py`, import-linter contracts, `test_architecture.py` | New routes and module are added to each |

## 3. Key design decisions (recommended)

### D1. Where it lives: a new `employer_portal` module
Mirrors `portal` (the youth portal). It owns membership, invites and the employer-facing views, and
calls `identity`, `employers`, `referrals`, and `intelligence`/`participants` services only.
- Keeps `employers` clean: CMP-05 forbids `employers` importing participants/referrals/intelligence,
  so the cross-domain views (referral + CV) cannot live there.
- Needs its own import-linter contract, the same way the youth portal has one.
- Alternative (rejected): put membership in `employers`. Simpler, but breaks CMP-05 as soon as
  referrals are shown.

### D2. Data model (new, in `employer_portal`)
- **`EmployerMember`**: `user` (OneToOne), `employer` (FK to `employers.Employer`, by id string through
  the employers service, not a hard cross-app FK if the linter objects), `job_title`, `is_owner`
  (bool, the first/lead user), `created_by`, `created_at`, `last_seen_at`.
  A user belongs to **one** employer at launch (see Q3).
- **`EmployerInvite`**: `member`, `email`, `token_hash`, `invited_by`, `expires_at`, `used_at`
  (same shape as `YouthInvite`).
- No change to `identity` tables; roles stay in `Role`/`RoleAssignment`.

### D3. Employer-side roles and permissions
New permission group **"Employer portal"** in `identity/catalogue.py`. Codes (one per action so the
authz matrix can name exactly one per route/method):

| Code | Allows |
|---|---|
| `employer.portal` | marker: this is an employer user (like `youth.self_service`); sign-in lands in the employer portal, MFA rule applies |
| `employer.view_dashboard` | dashboard and activity |
| `employer.view_profile` / `employer.edit_profile` | company profile and contacts |
| `employer.view_opportunities` / `employer.edit_opportunities` | list/read, create/edit/requirements |
| `employer.publish_opportunities` | open and close (separated so a recruiter can draft and a director publishes) |
| `employer.view_referrals` | referral list, candidate profile, CV |
| `employer.respond_referrals` | review, interview, select, reject, set interview details |
| `employer.manage_staff` | invite, suspend, change role of the company's own users |

Default employer roles (seeded as `is_system`, like the staff defaults):

| Role | Gets |
|---|---|
| **Company admin (Director/Owner)** | everything above |
| **HR / Recruiter** | dashboard, profile view, opportunities (view/edit/publish), referrals (view/respond); no staff management, no profile edit |
| **Hiring manager** | dashboard, opportunities view, referrals view/respond |
| **Viewer** | dashboard, profile, opportunities, referrals (read only) |

Employer roles are a **separate role family**: a company admin can only assign roles flagged
`employer_assignable`, never staff roles, and cannot create new roles or edit permissions
(PI staff keep that). This answers "manage the roles they can do" without letting a company
escalate itself. (Custom per-company roles: Q4.)

### D4. Employer scope ("their own records only")
Staff scope today is programme/cohort/region/officer via `ScopeAssignment`. Employers need a new,
simpler, **non-optional** scope: *everything is filtered by the user's own `employer_id`*.
- A single helper in `employer_portal` (`own_employer(user)`), used by **every** view and service.
  There is no "all" path for these users.
- Employer users hold only `employer.*` codes, so they cannot reach any staff route (the permission
  catalogue already blocks that), and the staff `scope_q` fallback (deny) protects against leaks.
- Isolation test: an employer user requesting another employer's opportunity/referral id gets 404.

### D5. What an employer may see and do with a referral
Principle: give enough to decide, never more than the CV rules already allow.

- **See:** the employer-safe CV (existing allow-list: no national ID, DOB, scores, support priority,
  assessments, admin notes), "why suggested" (plain-language fit factors; **never** the numeric score
  or rule versions), stage, interview details, the note staff wrote for the employer. Contact details
  only once the youth is **selected** or consent allows (Q5, data-protection decision).
- **Never see:** other employers, other referrals of the same youth, staff notes, support/risk data,
  match scores, officer names (show "PI360 placement team").
- **Do:** move to under review, interview (with date/place/note, shown to the youth), selected,
  rejected (controlled reason code, mandatory), "no response" is system/staff only. `placed` and
  `closed` remain staff actions (they confirm the real-world outcome). Every action writes the same
  `StageEvent` with the employer user as actor, so the youth's journey view and staff history keep
  working unchanged.
- **Staff are notified** on each employer decision; the youth's existing notices pick it up.

### D6. Company profile edits
Employers may edit address, website, sectors, counties and contacts. **Name and status stay
staff-only** (name changes feed duplicate detection and aliases; status is a PI decision).

### D7. Opportunities
Employer creates and edits their own opportunities with the same form and requirements/skills picker
staff use. Publishing is the open question Q6 (immediate vs staff approval). Default recommended:
**immediate for verified (active) employers**, with a staff notification, because staff already
control who is referred to it.

### D8. Account lifecycle and security
- **First user:** PI staff invite the company admin from the employer page (new permission
  `employers.invite_user`, held by Manager/Administrator). Email is to a contact address on the record.
- **Subsequent users:** the company admin invites from "Team" in the portal (`employer.manage_staff`).
- Invite link, expiry, one-time token, activation page: identical to youth.
- Suspend / reactivate / change role / resend / withdraw invite.
- **Last-admin protection:** cannot suspend, demote or remove the only remaining company admin.
- **Sessions/lockout:** existing lockout and session lifetime apply. MFA: recommended **required for
  Company admin**, optional for others (decision Q7); today `mfa.is_youth_only` exempts youth only,
  so employer-only users need an explicit rule there.
- **Audit:** every invite, role change, suspension and decision goes to the audit log (existing
  `audit.record`).
- **Offboarding:** when an employer is archived or set inactive, all its users are locked out
  immediately (checked at request time, not just at login).
- Email: invites use the existing mail backend (console until D-016/D-042 pick a provider, so
  dev/pilot invites must also be copyable as a link, same as youth).

## 4. API surface (all under `/api/v1/employer/...`)

Every route is permission-gated with exactly one code per method and added to
`tests/test_authz_matrix.py`.

| Route | Method: permission |
|---|---|
| `employer/activate/check`, `employer/activate` | public (token) |
| `employer/me` | GET: `employer.portal` |
| `employer/dashboard` | GET: `employer.view_dashboard` |
| `employer/dashboard/drilldown` | GET: `employer.view_dashboard` |
| `employer/profile` | GET: `employer.view_profile`; PATCH: `employer.edit_profile` |
| `employer/contacts[/<id>]` | GET: `employer.view_profile`; POST/PATCH/DELETE: `employer.edit_profile` |
| `employer/opportunities` | GET: `employer.view_opportunities`; POST: `employer.edit_opportunities` |
| `employer/opportunities/<id>` | GET: view; PATCH: edit |
| `employer/opportunities/<id>/transition` | POST: `employer.publish_opportunities` |
| `employer/opportunities/<id>/requirements[...]` | GET: view; POST/PATCH/DELETE: edit |
| `employer/referrals` | GET: `employer.view_referrals` |
| `employer/referrals/<id>` | GET: `employer.view_referrals` |
| `employer/referrals/<id>/cv`, `/cv.pdf`, `/photo` | GET: `employer.view_referrals` |
| `employer/referrals/<id>/transition` | POST: `employer.respond_referrals` |
| `employer/referrals/<id>/interview` | POST: `employer.respond_referrals` |
| `employer/staff` | GET/POST (invite): `employer.manage_staff` |
| `employer/staff/<id>` | PATCH (role, suspend, reactivate), DELETE (withdraw invite): `employer.manage_staff` |
| `employer/roles` | GET: `employer.manage_staff` (read-only list of assignable roles) |
| Staff side: `employers/<id>/users`, `employers/<id>/invite` | GET: `employers.view`; POST: `employers.invite_user` |

## 5. Dashboard

**Headline figures (each a link to the filtered list it counts):**

| Figure | Opens |
|---|---|
| Open opportunities | opportunities, status = open |
| Closing in 7 days | opportunities, closing soon |
| New referrals (awaiting your reply) | referrals, stage = submitted |
| In review | referrals, stage = under review |
| Interviews coming up | referrals, stage = interview, date ≥ today |
| Selected | referrals, stage = selected |
| Placed (year to date) | referrals, stage = placed |
| Median days to first reply | referrals, replied (the same list the median is computed from) |

**Analytics:**
- Referral funnel by stage (bar, each bar clickable).
- Referrals per opportunity (table, each row opens that opportunity's referrals).
- Trend: referrals received per week, last 12 weeks.
- Reply time vs the platform's service target (employers who respond fast keep getting candidates).

**Activity feed (clickable):** "3 new referrals for *Sales Associate*", "*Wanjiru K.* moved to
interview by *you*", "Opportunity *X* closes in 2 days", "Invite for *Peter* not yet accepted".
Each entry links to its record.

**Needs attention** strip at the top: referrals waiting > N days for a reply, opportunities with no
referrals, expired opportunities, pending invites.

**Implementation:** `employer_portal.services.dashboard(employer_id)` composes counts from
`employers` (opportunities), `referrals` (extend `employer_counts` and add `counts_by_stage` per
employer; the existing function already gives sent/replied/median/interview/placed) and
`audit` (activity). Drill-down reuses the `reporting` drilldown contract: the number and the list it
opens come from one query so they cannot disagree. Charts via the existing chart components; checked
with the `dataviz` guidelines (no colour-only meaning, accessible labels).

## 6. Frontend

New role-aware portal shell (reusing Metronic layout and `RequirePermission`):

- **Routing:** `employer.portal` users land on `/employer` (like `youth.self_service` lands on the
  portal today). Login page unchanged; the sign-in response decides the landing.
- **Pages:** Dashboard, Opportunities (list, new, edit, requirements), Referrals (list, detail with
  candidate card, CV download, respond), Company profile, Team (staff and roles), Account (password,
  MFA), Activate (invite link), Help.
- **Navigation filtered by permission** (a Viewer does not see "Team"; buttons for actions the role
  lacks are hidden, and the API enforces it anyway).
- **Staff side:** an "Employer users" tab on the employer page (invite first admin, see users,
  suspend, resend).
- Reuse: `candidate-profile.tsx`, `skill-picker`, opportunity form, `StatusBadge`, `states`.
- **Help guides:** new employer audience in the help centre (sign in, add a colleague, post an
  opportunity, respond to a referral, read the dashboard), per the "feature not done until its guide
  exists" rule.

## 7. Data protection and risk

| Risk | Control |
|---|---|
| Employer sees another employer's data | single `own_employer` helper, 404 on foreign ids, per-endpoint isolation tests |
| Over-sharing youth data | employer-specific serializer with an allow-list; contact details gated by stage/consent (Q5); test asserts forbidden keys are absent |
| Privilege escalation by a company admin | employer roles are a fixed family; admin cannot create roles or assign staff roles |
| Orphaned access after a user leaves | suspend/remove, employer inactive/archived locks everyone out, last-admin rule |
| Phishing/credential risk | lockout, MFA for company admin, short-lived invite tokens, no open registration |
| Employers gaming outcomes | placed/closed stay staff-confirmed; all moves go through the existing append-only `StageEvent` |
| Update to the data-protection review | `docs/data-protection-review.md` needs a section on employer users and a lawful-basis note before launch |

## 8. Phases (each independently shippable and tested)

1. **Foundations (backend).** `employer_portal` module, `EmployerMember`/`EmployerInvite`, catalogue
   codes, default roles, import-linter contract, invite/activate/suspend services, staff-side invite
   route, MFA/lockout rules, tests (isolation, last-admin, authz matrix). *~5 days*
2. **Employer-scoped data APIs.** profile + contacts, opportunities + requirements + transitions,
   referral list/detail/CV/respond with the employer-safe serializers. Tests that forbidden fields
   never appear. *~6 days*
3. **Team and roles management.** staff list, invite, role change, suspend, resend; employer roles
   endpoint; staff-side "Employer users" tab. *~3 days*
4. **Dashboard.** KPIs, funnel, trend, attention strip, activity feed, drilldown. *~4 days*
5. **Frontend portal.** shell, routing, pages for everything above, activate page, role-aware nav,
   component tests. *~8 days*
6. **Hardening and launch.** help guides, data-protection review update, seed/dev accounts, a full
   walkthrough with browser verification, accessibility check, openapi regenerated, pilot notes.
   *~3 days*

Total roughly **4 to 5 weeks** for one developer; phases 1 to 3 are the critical path and 4 and 5 can
overlap once the APIs exist.

## 9. Testing strategy

- Authz matrix: every new route, every role (Admin, HR, Hiring manager, Viewer, staff, youth,
  anonymous).
- Isolation: employer A cannot read or act on employer B's opportunity, referral, CV, staff, invite.
- Forbidden-field test on every employer-facing response (scores, national ID, DOB, staff notes).
- Last-admin and self-demotion rules; invite expiry and reuse; suspended employer locks users out.
- Referral actions: the employer can only perform transitions allowed for them; a reject without a
  reason is refused; the youth journey and staff history show the employer's action.
- Dashboard: every figure's drilldown row count equals the displayed number.
- Frontend: component tests for nav-by-role, guarded routes, forms; browser walkthrough per role.

## 10. Open questions (need your decision before build)

1. **The brief's fourth bullet was empty.** Was something meant to go there (e.g. notifications,
   messaging with PI staff, reports/export)?
2. **Who creates the first company account**: PI staff only (recommended), or may a company
   self-register and be approved by staff?
3. **One company per user** (recommended), or can one person (e.g. a recruiter agency) serve several
   companies?
4. **Roles:** are the four fixed employer roles (Company admin, HR/Recruiter, Hiring manager,
   Viewer) enough, or must each company be able to define custom roles?
5. **Candidate contact details:** show to the employer only once **selected** (recommended), after
   **interview**, or always? Needs a data-protection ruling.
6. **Publishing opportunities:** employers open them immediately (recommended, with a staff
   notification), or staff must approve first?
7. **MFA:** required for Company admin only (recommended), for everyone, or optional?
8. **Can employers move a referral to Placed**, or does staff confirm placement (recommended: staff)?
9. **Notifications:** email on new referral and on invite is assumed; in-app only until the email
   provider (D-016/D-042) is chosen. Acceptable for the pilot?

### Decisions recorded (2026-11-16)

| # | Question | Decision |
|---|---|---|
| 2 | Who creates the first company account | **PI staff only.** No self-registration. |
| 5 | Candidate contact details | Shown to the employer **only once the youth is selected**. |
| 6 | Publishing opportunities | **A setting** (`employer_self_publish`), **off by default**: staff approve an employer's opportunity before it is published. |
| 7 | MFA | **A setting** (`employer_mfa_required`), **off by default**. It can be limited to named roles (for example Company admin). |
| 1, 3, 4, 8, 9 | Fourth bullet, one company per user, fixed roles, who marks Placed, notifications | Not answered: the recommended defaults above apply (one company per user, four fixed roles, staff confirm Placed, email on invite and on new referral). |

Both settings are stored as feature flags (Configuration), so changes are audited and editable
by an administrator without a release. Phase 1 seeds them switched off.

## 11. Not in scope (unless you say otherwise)

Employer-initiated candidate search/browsing, messaging, billing, multi-company groups, custom
per-company roles, employer-side bulk import, public job board.
