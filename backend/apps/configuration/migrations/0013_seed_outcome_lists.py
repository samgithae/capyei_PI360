"""The employment types and reasons for leaving CAP-YEI approved (B25, PI360-NEW-034/035).

Seeded exactly as approved. Administrators can rename, retire or add entries as reference data;
codes are stable once used. Salary bands are not seeded: CAP-YEI approved recording a band (A3)
but has not given the ranges."""

from django.db import migrations

from apps.configuration.models import norm

EMPLOYMENT_TYPES = [
    # code, name, self_employment
    ("PERMANENT", "Permanent employment", False),
    ("CONTRACT", "Contract employment", False),
    ("TEMPORARY", "Temporary employment", False),
    ("CASUAL", "Casual employment", False),
    ("INTERNSHIP", "Internship", False),
    ("APPRENTICESHIP", "Apprenticeship", False),
    ("SELF", "Self-employment", True),
    ("OTHER", "Other", False),
]

LEAVING_REASONS = [
    # code, name, needs_note
    ("CONTRACT-COMPLETED", "Contract completed", False),
    ("RESIGNED", "Resigned voluntarily", False),
    ("DISMISSED", "Dismissed or terminated", False),
    ("REDUNDANCY", "Redundancy", False),
    ("EMPLOYER-CLOSED", "Employer closed or business ceased operations", False),
    ("OTHER-OPPORTUNITY", "Moved to another opportunity", False),
    ("PERSONAL", "Personal reasons", False),
    ("OTHER", "Other", True),
]


def seed(apps, schema_editor):
    types = apps.get_model("configuration", "EmploymentType")
    for code, name, self_employment in EMPLOYMENT_TYPES:
        types.objects.get_or_create(
            code=code,
            defaults={
                "name": name, "name_normalised": norm(name), "self_employment": self_employment,
            },
        )  # fmt: skip
    reasons = apps.get_model("configuration", "LeavingReason")
    for code, name, needs_note in LEAVING_REASONS:
        reasons.objects.get_or_create(
            code=code,
            defaults={"name": name, "name_normalised": norm(name), "needs_note": needs_note},
        )


def unseed(apps, schema_editor):
    apps.get_model("configuration", "EmploymentType").objects.filter(
        code__in=[r[0] for r in EMPLOYMENT_TYPES]
    ).delete()
    apps.get_model("configuration", "LeavingReason").objects.filter(
        code__in=[r[0] for r in LEAVING_REASONS]
    ).delete()


class Migration(migrations.Migration):
    dependencies = [("configuration", "0012_outcome_reference_lists")]
    operations = [migrations.RunPython(seed, unseed)]
