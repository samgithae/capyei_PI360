"""The personal details a youth may change on their own record.

Allowed: names, gender, date of birth, home county, where they live now, and their contacts.
Left to staff on purpose (they affect eligibility, reporting or who can sign in): the status,
enrollments (programme, cohort, course, institution, enrollment number, dates, exit reason),
the assigned officer, archiving, verification, and the e-mail the account signs in with.
Audit entries record which fields changed, never the values of contacts."""

from django.db import transaction
from django.utils import timezone

from apps.audit import services as audit
from apps.configuration import services as configuration

from .models import Participant, ParticipantContact, ParticipantResidence

NAME_FIELDS = ("given_name", "family_name", "other_names")


class DetailsError(ValueError):
    def __init__(self, message, field="details"):
        super().__init__(message)
        self.field = field


def read_own(p: Participant) -> dict:
    res = p.residences.filter(valid_to__isnull=True).select_related("county").first()
    return {
        "full_name": p.full_name_source,
        "given_name": p.given_name,
        "family_name": p.family_name,
        "other_names": p.other_names,
        "gender": p.gender,
        "date_of_birth": p.date_of_birth.isoformat() if p.date_of_birth else None,
        "county_id": str(p.origin_county_id) if p.origin_county_id else "",
        "residence": {
            "county_id": str(res.county_id) if res and res.county_id else "",
            "sub_county": res.sub_county_source if res else "",
            "ward": res.ward_source if res else "",
        },
        "contacts": [
            {"kind": c.kind, "value": c.value, "primary": c.is_primary} for c in p.contacts.all()
        ],
        "counties": [
            {"id": c["id"], "name": c["name"]} for c in configuration.filter_options()["counties"]
        ],
        "genders": [{"value": v, "label": label} for v, label in Participant.GENDERS],
    }


@transaction.atomic
def write_own(*, actor, p: Participant, data: dict) -> dict:
    changed = []
    simple = {k: data[k] for k in (*NAME_FIELDS, "gender", "date_of_birth") if k in data}
    if "full_name" in data and data["full_name"].strip():
        simple["full_name_source"] = data["full_name"].strip()
    if "county_id" in data:
        cid = data["county_id"]
        if cid is not None and not configuration.county_exists(cid):
            raise DetailsError("Unknown county.", "county_id")
        simple["origin_county_id"] = cid
    for k, v in simple.items():
        if getattr(p, k) != v:
            setattr(p, k, v)
            changed.append(k)
    if changed:
        p.save()

    res = data.get("residence")
    if res is not None:
        cid = res.get("county_id")
        if cid is not None and not configuration.county_exists(cid):
            raise DetailsError("Unknown county.", "residence")
        cur = p.residences.filter(valid_to__isnull=True).first()
        new = (cid, res.get("sub_county", "").strip(), res.get("ward", "").strip())
        if not cur or (cur.county_id, cur.sub_county_source, cur.ward_source) != new:
            if cur:
                cur.valid_to = timezone.localdate()
                cur.save(update_fields=["valid_to"])
            ParticipantResidence.objects.create(
                participant=p,
                county_id=new[0],
                sub_county_source=new[1],
                ward_source=new[2],
                valid_from=timezone.localdate(),
            )
            changed.append("residence")

    rows = data.get("contacts")
    if rows is not None:
        old = [(c.kind, c.value.strip().lower(), c.is_primary) for c in p.contacts.all()]
        new = [(r["kind"], r["value"].strip().lower(), r["primary"]) for r in rows]
        if sorted(old) != sorted(new):
            p.contacts.all().delete()
            ParticipantContact.objects.bulk_create(
                ParticipantContact(
                    participant=p, kind=r["kind"], value=r["value"].strip(), is_primary=r["primary"]
                )
                for r in rows
            )
            changed.append("contacts")

    if changed:
        audit.record(
            actor=actor,
            action="youth.details_edited",
            object_type="participant",
            object_id=p.pk,
            after={"fields": changed},
        )
    return read_own(p)
