"""Proposed starting grades for each qualification level.

Working list until CAP-YEI confirms it. Rank is within the level, higher is better. Primary has
no grades. Administrators can rename, retire or add grades (Administration menu)."""

from django.db import migrations

from apps.configuration.models import grade_key

SECONDARY = ["E", "D-", "D", "D+", "C-", "C", "C+", "B-", "B", "B+", "A-", "A"]
CERT = ["Pass", "Credit", "Distinction"]
DEGREE = ["Pass", "Second class lower", "Second class upper", "First class"]

# level code -> (code prefix, grade names from lowest to highest)
GRADES = {
    "QL02": ("SEC", SECONDARY),
    "QL03": ("ART", CERT),
    "QL04": ("CRF", CERT),
    "QL05": ("DIP", CERT),
    "QL06": ("HDP", CERT),
    "QL07": ("BSC", DEGREE),
    "QL08": ("PGD", CERT),
    "QL09": ("MSC", CERT),
}


def code_for(prefix, name):
    return f"{prefix}-{name}".upper().replace(" ", "-")[:40]


def seed(apps, schema_editor):
    level = apps.get_model("configuration", "QualificationLevel")
    grade = apps.get_model("configuration", "QualificationGrade")
    for lcode, (prefix, names) in GRADES.items():
        row = level.objects.filter(code=lcode).first()
        if row is None:
            continue
        for rank, name in enumerate(names, start=1):
            grade.objects.get_or_create(
                code=code_for(prefix, name),
                defaults={"level": row, "name": name, "name_normalised": grade_key(name), "rank": rank},
            )


def unseed(apps, schema_editor):
    codes = [code_for(p, n) for p, names in GRADES.values() for n in names]
    apps.get_model("configuration", "QualificationGrade").objects.filter(code__in=codes).delete()


class Migration(migrations.Migration):
    dependencies = [("configuration", "0006_qualification_grade")]
    operations = [migrations.RunPython(seed, unseed)]
