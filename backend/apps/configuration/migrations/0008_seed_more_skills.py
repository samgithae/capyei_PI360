"""A fuller starting list of skills for the requirement picker.

The first twelve skills are too few to browse by category. These are working additions in the same
categories (plus "Core competencies" for the soft skills employers ask for); administrators can
rename, retire or add more. A skill is skipped when its code, or the same name in any spelling,
already exists, so running this on a list that has been edited by hand changes nothing there.
Reversing removes only the skills added here that no opportunity or CV uses."""

from django.db import migrations
from django.db.models import ProtectedError

from apps.configuration.models import norm

SKILLS = [
    # code, name, category
    ("SK-CASHIER", "Cash handling", "Service"),
    ("SK-RECEPTION", "Reception and front desk", "Service"),
    ("SK-MERCH", "Shelf stocking and merchandising", "Service"),
    ("SK-PHONE", "Telephone and call handling", "Service"),
    ("SK-CLEANING", "Cleaning and sanitation", "Service"),
    ("SK-SECURITY", "Security and guarding", "Service"),
    ("SK-COOKING", "Cooking", "Hospitality"),
    ("SK-BAKING", "Baking and pastry", "Hospitality"),
    ("SK-BARISTA", "Bar and beverage service", "Hospitality"),
    ("SK-WAITING", "Waiting and table service", "Hospitality"),
    ("SK-FOODSAFE", "Food safety and hygiene", "Hospitality"),
    ("SK-TYPING", "Typing and data entry", "Office"),
    ("SK-SPREADSHEET", "Spreadsheets", "Office"),
    ("SK-FILING", "Filing and records", "Office"),
    ("SK-SOCIAL", "Social media", "Office"),
    ("SK-MASONRY", "Masonry and bricklaying", "Trades"),
    ("SK-PAINTING", "Painting and decorating", "Trades"),
    ("SK-MECHANIC", "Motor vehicle repair", "Trades"),
    ("SK-HAIR", "Hairdressing and barbering", "Trades"),
    ("SK-BEAUTY", "Beauty therapy", "Trades"),
    ("SK-MOTORBIKE", "Motorcycle riding", "Transport"),
    ("SK-DELIVERY", "Delivery and courier work", "Transport"),
    ("SK-WAREHOUSE", "Warehouse and stores", "Transport"),
    ("SK-FARMING", "Crop and livestock farming", "Agriculture"),
    ("SK-AGROPROC", "Farm produce handling", "Agriculture"),
    ("SK-COMM", "Communication", "Core competencies"),
    ("SK-TEAMWORK", "Teamwork", "Core competencies"),
    ("SK-TIME", "Time management", "Core competencies"),
    ("SK-PROBLEM", "Problem solving", "Core competencies"),
    ("SK-LEADERSHIP", "Leadership", "Core competencies"),
    ("SK-ENTREPRENEUR", "Entrepreneurship", "Core competencies"),
    ("SK-LANG-SW", "Kiswahili and English fluency", "Core competencies"),
]


def seed(apps, schema_editor):
    skill = apps.get_model("configuration", "Skill")
    for code, name, category in SKILLS:
        if skill.objects.filter(code=code).exists():
            continue
        if skill.objects.filter(name_normalised=norm(name)).exists():
            continue
        skill.objects.create(
            code=code, name=name, name_normalised=norm(name), category=category
        )


def unseed(apps, schema_editor):
    skill = apps.get_model("configuration", "Skill")
    for row in skill.objects.filter(code__in=[r[0] for r in SKILLS]):
        try:
            row.delete()
        except ProtectedError:
            pass  # in use by an opportunity or a CV: keep it


class Migration(migrations.Migration):
    dependencies = [("configuration", "0007_seed_qualification_grades")]
    operations = [migrations.RunPython(seed, unseed)]
