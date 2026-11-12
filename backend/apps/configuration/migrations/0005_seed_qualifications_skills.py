"""Proposed starting lists of qualification levels and skills.

Working lists until CAP-YEI confirms them. Administrators can rename, retire or add entries
(Administration menu) or load more from a file; codes are stable once used."""

from django.db import migrations

from apps.configuration.models import norm

LEVELS = [
    # code, name, rank (higher = more advanced)
    ("QL01", "Primary education", 1),
    ("QL02", "Secondary education (KCSE or equivalent)", 2),
    ("QL03", "Artisan or basic certificate", 3),
    ("QL04", "Craft certificate", 4),
    ("QL05", "Diploma", 5),
    ("QL06", "Higher diploma", 6),
    ("QL07", "Bachelor's degree", 7),
    ("QL08", "Postgraduate diploma", 8),
    ("QL09", "Master's degree", 9),
    ("QL10", "Doctorate", 10),
]

SKILLS = [
    # code, name, category
    ("SK-CUSTOMER", "Customer service", "Service"),
    ("SK-SALES", "Sales", "Service"),
    ("SK-FOOD", "Food preparation", "Hospitality"),
    ("SK-HOUSEKEEP", "Housekeeping", "Hospitality"),
    ("SK-COMPUTER", "Basic computer skills", "Office"),
    ("SK-BOOKKEEP", "Bookkeeping", "Office"),
    ("SK-WELDING", "Welding", "Trades"),
    ("SK-ELECTRICAL", "Electrical installation", "Trades"),
    ("SK-PLUMBING", "Plumbing", "Trades"),
    ("SK-CARPENTRY", "Carpentry", "Trades"),
    ("SK-TAILORING", "Tailoring", "Trades"),
    ("SK-DRIVING", "Driving", "Transport"),
]


def seed(apps, schema_editor):
    level = apps.get_model("configuration", "QualificationLevel")
    for code, name, rank in LEVELS:
        level.objects.get_or_create(
            code=code, defaults={"name": name, "name_normalised": norm(name), "rank": rank}
        )
    skill = apps.get_model("configuration", "Skill")
    for code, name, category in SKILLS:
        skill.objects.get_or_create(
            code=code,
            defaults={"name": name, "name_normalised": norm(name), "category": category},
        )


def unseed(apps, schema_editor):
    apps.get_model("configuration", "QualificationLevel").objects.filter(
        code__in=[r[0] for r in LEVELS]
    ).delete()
    apps.get_model("configuration", "Skill").objects.filter(
        code__in=[r[0] for r in SKILLS]
    ).delete()


class Migration(migrations.Migration):
    dependencies = [("configuration", "0004_qualification_levels_skills")]
    operations = [migrations.RunPython(seed, unseed)]
