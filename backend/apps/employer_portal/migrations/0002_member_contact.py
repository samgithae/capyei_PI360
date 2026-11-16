import django.db.models.deletion
from django.db import migrations, models


def link_members(apps, schema_editor):
    """One person, one record. Each existing sign-in is matched to the contact with the same
    e-mail address at the same employer; a sign-in with no matching contact gets one."""
    Member = apps.get_model("employer_portal", "EmployerMember")
    Contact = apps.get_model("employers", "EmployerContact")
    linked = set()
    for member in Member.objects.select_related("user").order_by("created_at"):
        email = (member.user.email or "").strip()
        match = (
            Contact.objects.filter(employer_id=member.employer_id, email__iexact=email)
            .exclude(pk__in=linked)
            .order_by("-is_primary", "name")
            .first()
        )
        if match is None:
            match = Contact.objects.create(
                employer_id=member.employer_id,
                name=member.full_name,
                role=member.job_title,
                email=email,
                phone="",
                is_primary=False,
            )
        else:
            # The account holds the name and e-mail the person signs in with; bring the contact
            # into line so both sides read the same.
            match.name, match.email = member.full_name, email
            if member.job_title:
                match.role = member.job_title
            match.save(update_fields=["name", "email", "role"])
        member.contact_id = match.pk
        member.save(update_fields=["contact"])
        linked.add(match.pk)


class Migration(migrations.Migration):

    dependencies = [
        ("employer_portal", "0001_initial"),
        ("employers", "0010_opportunity_publish_request"),
    ]

    operations = [
        migrations.AddField(
            model_name="employermember",
            name="contact",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="portal_member",
                to="employers.employercontact",
            ),
        ),
        migrations.RunPython(link_members, migrations.RunPython.noop),
    ]
