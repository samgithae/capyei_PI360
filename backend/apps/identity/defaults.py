"""Proposed starting roles from doc 18 §3. Roles are data: administrators can change them.
D-014 (scopes) and D-024 (role catalogue) are open, so treat these as defaults."""

STAFF_VIEW = [
    "participants.view",
    "participants.view_contact",
    "participants.view_profile",
    "placements.view",
    "employers.view",
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
            "config.view",
            "config.manage",
            "config.manage_protected",
            "reference.manage",
            "participants.view",
            "placements.view",
            "employers.view",
            "reports.view_aggregate",
        ],
    },
    {
        "name": "Data steward",
        "description": "Runs imports, resolves duplicates, maintains reference data.",
        "scope_mode": "all",
        "active": True,
        "permissions": STAFF_VIEW
        + [
            "participants.edit",
            "participants.import",
            "placements.edit",
            "employers.edit",
            "imports.run",
            "imports.commit",
            "duplicates.review",
            "duplicates.merge",
            "reference.manage",
            "reports.view_aggregate",
        ],
    },
    {
        "name": "Placement officer",
        "description": "Works a caseload within assigned scope.",
        "scope_mode": "assigned",
        "active": True,
        "permissions": STAFF_VIEW
        + [
            "participants.edit",
            "placements.edit",
            "employers.edit",
            "referrals.view",
            "referrals.edit",
            "intelligence.view",
            "reports.view_aggregate",
        ],
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
]
