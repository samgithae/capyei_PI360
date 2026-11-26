"""Proposed starting roles from doc 18 §3. Roles are data: administrators can change them.
D-014 (scopes) and D-024 (role catalogue) are open, so treat these as defaults."""

STAFF_VIEW = [
    "participants.view",
    "participants.view_contact",
    "participants.view_profile",
    "placements.view",
    "employers.view",
]

# An administrator can do everything a steward or officer can (referral approval stays a manager
# action) and is the only default role that may archive. Editable in Roles like any other.
ADMIN_ALSO = [
    "participants.edit",
    "participants.invite",
    "employers.invite_user",
    "employers.view_feedback_notes",
    "employers.review",
    "participants.import",
    "placements.edit",
    "employers.edit",
    "imports.run",
    "imports.commit",
    "duplicates.review",
    "duplicates.merge",
    "dataquality.review",
    "referrals.view",
    "referrals.edit",
    "intelligence.view",
    "reports.view_aggregate",
    "records.archive",
    "exports.deidentified",
]

PLACEMENT_OFFICER = STAFF_VIEW + [
    "participants.edit",
    "placements.edit",
    "employers.edit",
    "employers.view_feedback_notes",
    "imports.run",
    "imports.commit",
    "referrals.view",
    "referrals.edit",
    "intelligence.view",
    "reports.view_aggregate",
]

# Rule versions (T-047). Who approves rules is D-009; until it is answered the administrator
# both drafts and approves. Split the two permissions across roles to get a second pair of eyes.
RULES = ["intelligence.manage_rules", "intelligence.approve_rules"]

# The employer portal roles. Each holds only ``employer.*`` codes, which is what lets a company
# admin assign them (never a staff role). The first role is the one with ``employer.manage_staff``.
EMPLOYER_BASE = [
    "employer.portal",
    "employer.view_dashboard",
    "employer.view_profile",
    "employer.view_opportunities",
    "employer.view_referrals",
]

DEFAULT_ROLES = [
    {
        "name": "Administrator",
        "description": "Manages users, roles, configuration and reference data.",
        "scope_mode": "all",
        "active": True,
        "permissions": [
            "identity.view_users",
            "identity.manage_users",
            "identity.manage_roles",
            "audit.view",
            "retention.view",
            "retention.manage",
            "config.view",
            "config.manage",
            "config.manage_protected",
            "reference.manage",
        ]
        + RULES
        + STAFF_VIEW
        + ADMIN_ALSO,
    },
    {
        "name": "Data steward",
        "description": "Runs imports, resolves duplicates, maintains reference data.",
        "scope_mode": "all",
        "active": True,
        "permissions": STAFF_VIEW
        + [
            "participants.edit",
            "participants.invite",
            "employers.invite_user",
            "employers.view_feedback_notes",
            "participants.import",
            "placements.edit",
            "employers.edit",
            "imports.run",
            "imports.commit",
            "duplicates.review",
            "duplicates.merge",
            "dataquality.review",
            "config.view",  # the reference lists it maintains are read through this
            "reference.manage",
            "reports.view_aggregate",
        ],
    },
    {
        "name": "Placement officer",
        "description": "Works a caseload within assigned scope.",
        "scope_mode": "assigned",
        "active": True,
        "permissions": list(PLACEMENT_OFFICER),
    },
    {
        "name": "Project officer",
        "description": "A placement officer limited to the projects assigned to them (D-085). "
        "Sees youth enrolled in those projects, including youth shared with another project. "
        "No project assigned means no access. Identifiable export is a grant to a named person, "
        "not part of this role (C-2).",
        "scope_mode": "assigned",
        "active": True,
        "permissions": list(PLACEMENT_OFFICER),
    },
    {
        "name": "Manager",
        "description": "Supervises team caseloads, reassigns work, approves selected actions.",
        "scope_mode": "assigned",
        "active": True,
        "permissions": STAFF_VIEW
        + [
            "referrals.view",
            "referrals.approve",
            "caseload.reassign",
            "intelligence.view",
            "reports.view_aggregate",
        ],
    },
    {
        "name": "M&E analyst",
        "description": "Aggregate indicators and de-identified exports only.",
        "scope_mode": "all",
        "active": True,
        "permissions": ["reports.view_aggregate", "exports.deidentified", "intelligence.view"],
    },
    {
        "name": "Assessor",
        "description": "Records YDM assessments for assigned cohorts. Off until D-024 confirms it.",
        "scope_mode": "assigned",
        "active": False,
        "permissions": ["participants.view", "ydm.assess"],
    },
    {
        "name": "Youth",
        "description": "A youth signed in to their own record. Sees and edits only that record.",
        "scope_mode": "assigned",
        "active": True,
        "permissions": ["youth.self_service"],
    },
    {
        "name": "Company admin",
        "description": "Employer director or owner: everything in the employer portal, including "
        "inviting colleagues and choosing their roles.",
        "scope_mode": "assigned",
        "active": True,
        "permissions": EMPLOYER_BASE
        + [
            "employer.edit_profile",
            "employer.edit_opportunities",
            "employer.publish_opportunities",
            "employer.respond_referrals",
            "employer.manage_staff",
        ],
    },
    {
        "name": "HR / Recruiter",
        "description": "Employer HR: manages opportunities and responds to referrals.",
        "scope_mode": "assigned",
        "active": True,
        "permissions": EMPLOYER_BASE
        + [
            "employer.edit_opportunities",
            "employer.publish_opportunities",
            "employer.respond_referrals",
        ],
    },
    {
        "name": "Hiring manager",
        "description": "Employer hiring manager: reads opportunities and responds to referrals.",
        "scope_mode": "assigned",
        "active": True,
        "permissions": EMPLOYER_BASE + ["employer.respond_referrals"],
    },
    {
        "name": "Employer viewer",
        "description": "Employer user who can read the dashboard, opportunities and referrals.",
        "scope_mode": "assigned",
        "active": True,
        "permissions": EMPLOYER_BASE,
    },
]
