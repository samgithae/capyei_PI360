# Audit coverage list (SEC-09, FR-17)

What must be written through `apps.audit.services.record`. A row turns to "wired" in the PR
that adds the call and a test that proves the event is written. Verified by review at each
gate (G3, G4).

| Area (SEC-09) | Example actions | Wired by | Status |
|---|---|---|---|
| Authentication | `auth.login`, `auth.login_failed`, `auth.lockout`, `auth.mfa_enrolled` | T-034 | pending |
| Permissions, roles, users | `user.created`, `user.suspended`, `role.changed`, `scope.assigned` | T-035, T-036 | pending |
| Profiles | `participant.edited`, `participant.merged`, `participant.unmerged` | T-043, T-041 | pending |
| Assessments | `assessment.submitted`, `assessment.amended` | T-049 | pending |
| Import jobs | `import.approved`, `import.committed`, `import.rolled_back` | T-040 | pending |
| Rules | `rule.activated`, `rule.retired` | T-047 | pending |
| Referrals | `referral.stage_changed`, `referral.corrected` (FR-17) | T-046 | pending |
| Overrides | `match.overridden` | T-144 | pending |
| Outcomes | `placement.recorded`, `placement.corrected` | later M3 | pending |
| Configuration | `setting.changed` (protected), `flag.changed` | T-039 | pending |
| Exports | `export.requested`, `export.downloaded` | M4 | pending |

Rules for callers: pass IDs and changed fields only; never secrets, passwords or whole records;
record inside the same transaction as the change; give a reason where the action needs one.
