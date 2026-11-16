"""Data step: carry each employer's and opportunity's single county and sector into the new links.
Kept apart from the schema steps so each runs in its own transaction."""

from django.db import migrations


def copy_single_to_many(apps, schema_editor):
    """Every existing single county / sector becomes a one-item link. Nothing is invented: rows
    with no value get no link, and the old columns stay until this has run (they are dropped by
    the operations after it)."""
    for model, link, owner in (
        ("Employer", "EmployerCounty", "employer"),
        ("Employer", "EmployerSector", "employer"),
        ("Opportunity", "OpportunityCounty", "opportunity"),
        ("Opportunity", "OpportunitySector", "opportunity"),
    ):
        field = "county" if link.endswith("County") else "sector"
        source, through = apps.get_model("employers", model), apps.get_model("employers", link)
        rows = source.objects.exclude(**{f"{field}__isnull": True}).values_list("pk", f"{field}_id")
        through.objects.bulk_create(
            [through(**{f"{owner}_id": pk, f"{field}_id": ref}) for pk, ref in rows],
            ignore_conflicts=True,
            batch_size=500,
        )


def copy_first_back(apps, schema_editor):
    """Reverse: a single column can hold one value, so keep the first link (by name) of each."""
    for model, link, owner in (
        ("Employer", "EmployerCounty", "employer"),
        ("Employer", "EmployerSector", "employer"),
        ("Opportunity", "OpportunityCounty", "opportunity"),
        ("Opportunity", "OpportunitySector", "opportunity"),
    ):
        field = "county" if link.endswith("County") else "sector"
        source, through = apps.get_model("employers", model), apps.get_model("employers", link)
        seen = set()
        for row in through.objects.order_by(f"{field}__name", "pk"):
            owner_id = getattr(row, f"{owner}_id")
            if owner_id in seen:
                continue
            seen.add(owner_id)
            source.objects.filter(pk=owner_id).update(**{f"{field}_id": getattr(row, f"{field}_id")})



class Migration(migrations.Migration):
    dependencies = [("employers", "0007_multi_county_multi_sector")]

    operations = [migrations.RunPython(copy_single_to_many, copy_first_back)]
