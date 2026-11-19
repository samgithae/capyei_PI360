"""Permission catalogue (FR-04, SEC-05). Defined in code; roles are data and pick from it.

``grant_only`` permissions can never be put in a role. They are given to a named user for a
stated purpose and expiry (doc 18 §4, SEC-18)."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Permission:
    code: str
    label: str
    group: str
    grant_only: bool = False


CATALOGUE: tuple[Permission, ...] = (
    Permission("identity.view_users", "View staff accounts", "Administration"),
    Permission("identity.manage_users", "Create, edit and suspend staff", "Administration"),
    Permission("identity.manage_roles", "Manage roles and scopes", "Administration"),
    Permission("audit.view", "View the audit log", "Administration"),
    Permission("retention.view", "View data-retention rules and runs", "Administration"),
    Permission("retention.manage", "Set, approve and run data-retention rules", "Administration"),
    Permission("config.view", "View configuration", "Administration"),
    Permission("config.manage", "Change configuration", "Administration"),
    Permission("config.manage_protected", "Change protected settings", "Administration"),
    Permission("reference.manage", "Manage reference data", "Administration"),
    Permission(
        "participants.view", "View participants (identity, programme, outreach)", "Participants"
    ),
    Permission("participants.edit", "Edit participants", "Participants"),
    Permission("participants.view_contact", "View participant contact details", "Participants"),
    Permission(
        "participants.view_profile", "View education, work history and activity", "Participants"
    ),
    Permission("participants.import", "Import participants", "Participants"),
    Permission("participants.invite", "Invite a youth to sign in", "Participants"),
    # Held only by the Youth role: the signed-in youth's own record, nothing else.
    Permission("youth.self_service", "Use the youth self-service portal", "Youth portal"),
    # Held only by the employer roles: a signed-in employer user sees and acts on their own
    # company's records, nothing else. The portal checks the company on every request.
    Permission("employer.portal", "Use the employer portal", "Employer portal"),
    Permission("employer.view_dashboard", "View the company dashboard", "Employer portal"),
    Permission("employer.view_profile", "View the company profile", "Employer portal"),
    Permission("employer.edit_profile", "Edit the company profile", "Employer portal"),
    Permission(
        "employer.view_opportunities", "View the company's opportunities", "Employer portal"
    ),
    Permission(
        "employer.edit_opportunities",
        "Create and edit the company's opportunities",
        "Employer portal",
    ),
    Permission(
        "employer.publish_opportunities",
        "Open and close the company's opportunities",
        "Employer portal",
    ),
    Permission("employer.view_referrals", "View referrals sent to the company", "Employer portal"),
    Permission(
        "employer.respond_referrals",
        "Respond to referrals (review, interview, decide)",
        "Employer portal",
    ),
    Permission(
        "employer.manage_staff", "Invite and manage the company's portal users", "Employer portal"
    ),
    Permission("placements.view", "View placements", "Placements"),
    Permission("placements.edit", "Record and edit placements", "Placements"),
    Permission("employers.view", "View employers and opportunities", "Employers"),
    Permission("employers.edit", "Edit employers and opportunities", "Employers"),
    Permission(
        "employers.invite_user", "Invite and manage an employer's portal users", "Employers"
    ),
    Permission("referrals.view", "View referrals", "Referrals"),
    Permission("referrals.edit", "Create and update referrals", "Referrals"),
    Permission("referrals.approve", "Approve selected referral actions", "Referrals"),
    Permission("caseload.reassign", "Reassign caseloads", "Referrals"),
    Permission("imports.run", "Upload, map and validate imports", "Data"),
    Permission("imports.commit", "Approve and commit imports", "Data"),
    Permission("duplicates.review", "Review duplicate candidates", "Data"),
    Permission("duplicates.merge", "Merge and unmerge records", "Data"),
    Permission("records.archive", "Archive and restore records", "Data"),
    Permission("ydm.view", "View YDM assessments", "YDM"),
    Permission("ydm.assess", "Record YDM assessments", "YDM"),
    Permission("ydm.manage", "Manage YDM instruments", "YDM"),
    Permission("intelligence.view", "View flags and recommendations", "Intelligence"),
    Permission("intelligence.manage_rules", "Draft and edit rule versions", "Intelligence"),
    Permission("intelligence.approve_rules", "Approve and activate rule versions", "Intelligence"),
    Permission("reports.view_aggregate", "View aggregate indicators", "Reporting"),
    Permission("exports.deidentified", "Export de-identified data", "Reporting"),
    # Restricted: only by grant (purpose + expiry), never through a role.
    Permission(
        "restricted.view_background",
        "View household, health and economic data (G7-G9)",
        "Restricted",
        True,
    ),
    Permission("restricted.view_national_id", "View full national ID (G10)", "Restricted", True),
    Permission("exports.identifiable", "Export identifiable data", "Restricted", True),
)

BY_CODE = {p.code: p for p in CATALOGUE}
GRANT_ONLY = frozenset(p.code for p in CATALOGUE if p.grant_only)
ROLE_ASSIGNABLE = frozenset(BY_CODE) - GRANT_ONLY
