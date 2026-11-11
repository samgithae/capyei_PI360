"""Proposed default reason codes for unsuccessful referrals (FR-18).

Working list until CAP-YEI confirms it (D-037). Administrators can rename, deactivate or add
codes as reference data; codes are stable once used."""

from django.db import migrations

from apps.configuration.models import norm

REASONS = [
    # code, name, applies_to, needs_note
    ("REJ-SKILLS", "Skills or qualification gap", "rejected", False),
    ("REJ-EXPERIENCE", "Not enough experience", "rejected", False),
    ("REJ-ASSESSMENT", "Did not pass the interview or assessment", "rejected", False),
    ("REJ-OTHER-CANDIDATE", "Employer chose another candidate", "rejected", False),
    ("WDR-DECLINED", "Youth declined the opportunity", "withdrawn", False),
    ("WDR-DISTANCE", "Distance or transport cost", "withdrawn", False),
    ("WDR-STUDY", "Youth chose further study", "withdrawn", False),
    ("WDR-OTHER-JOB", "Youth took another job", "withdrawn", False),
    ("WDR-CANCELLED", "Employer cancelled the opportunity", "withdrawn", False),
    ("NOR-EMPLOYER", "Employer did not respond", "no_response", False),
    ("NOR-YOUTH", "Youth could not be reached", "no_response", False),
    ("OTHER", "Other (explain in the note)", "any", True),
]


def seed(apps, schema_editor):
    model = apps.get_model("configuration", "ReferralReason")
    for code, name, applies_to, needs_note in REASONS:
        model.objects.get_or_create(
            code=code,
            defaults={
                "name": name,
                "name_normalised": norm(name),
                "applies_to": applies_to,
                "needs_note": needs_note,
            },
        )


def unseed(apps, schema_editor):
    apps.get_model("configuration", "ReferralReason").objects.filter(
        code__in=[r[0] for r in REASONS]
    ).delete()


class Migration(migrations.Migration):
    dependencies = [("configuration", "0002_referral_reason")]
    operations = [migrations.RunPython(seed, unseed)]
