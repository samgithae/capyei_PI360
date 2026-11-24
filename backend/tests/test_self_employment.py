"""D-080 / B27 (PI360-NEW-071): self-employment is its own placement outcome.

Its facts (business name, activity, date started, operational status, evidence, income where
available, verification) are kept on the self-employment pathway only, never on wage
employment. Income is economic data: it needs the grant-only restricted.view_background
permission to read or write, and the audit trail says only whether it is recorded. All data
here is synthetic."""

from datetime import date, timedelta

import pytest
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.identity import services as identity
from apps.placements import services as placements
from apps.placements.models import Placement

from .test_casework import JSON, PL, client_for, enrollment, manager, officer, youth  # noqa: F401
from .test_participants import world  # noqa: F401

BUSINESS = {
    "pathway": "self_employment",
    "start_date": "2026-02-01",
    "employer_name_source": "Test Tailoring",
    "business_activity": "Tailoring and repairs",
    "operational_status": "operating",
    "business_evidence": "Officer visited the stall.",
}


def give_income_grant(user, make_user):
    admin = make_user("admin-grant", "Administrator")
    identity.grant_permission(
        actor=admin, user=user, permission="restricted.view_background",
        purpose="Self-employment follow-up", expires_at=timezone.now() + timedelta(days=3),
    )  # fmt: skip


def create(c, youth, **kw):  # noqa: F811
    return c.post(PL, {"participant_id": str(youth.pk), **BUSINESS, **kw}, content_type=JSON)


def test_records_the_business_facts_on_self_employment(officer, youth, enrollment):  # noqa: F811
    r = create(client_for(officer), youth)
    assert r.status_code == 201, r.content
    body = r.json()
    assert body["employer"] == "Test Tailoring" and body["pathway"] == "self_employment"
    assert body["business_activity"] == "Tailoring and repairs"
    assert body["operational_status_label"] == "Operating"
    assert body["monthly_income"] is None and body["can"]["income"] is False


def test_business_details_are_refused_on_wage_employment(officer, youth, enrollment):  # noqa: F811
    r = create(client_for(officer), youth, pathway="wage")
    assert r.status_code == 409
    assert "self-employment" in r.json()["errors"][0]["message"]


def test_income_needs_the_restricted_grant(officer, youth, enrollment, make_user):  # noqa: F811
    c = client_for(officer)
    r = create(c, youth, monthly_income="4500.00")
    assert r.status_code == 409 and r.json()["errors"][0]["field"] == "monthly_income"
    assert Placement.objects.count() == 0

    give_income_grant(officer, make_user)
    r = create(c, youth, monthly_income="4500.00")
    assert r.status_code == 201
    assert r.json()["monthly_income"] == "4500.00" and r.json()["can"]["income"] is True


def test_income_is_hidden_from_staff_without_the_grant(  # noqa: F811
    officer, manager, youth, enrollment, make_user  # noqa: F811
):  # fmt: skip
    give_income_grant(officer, make_user)
    pid = create(client_for(officer), youth, monthly_income="4500.00").json()["id"]
    body = client_for(manager).get(f"{PL}/{pid}").json()
    assert body["monthly_income"] is None and body["business_activity"]


def test_audit_keeps_whether_income_is_recorded_not_the_amount(enrollment):  # noqa: F811
    p = placements.record_manual(
        actor=None, enrollment_id=enrollment.pk, pathway="self_employment",
        start_date=date(2026, 1, 1), employer_name_source="Test Kiosk", monthly_income=3000,
    )  # fmt: skip
    after = AuditEvent.objects.get(action="placement.recorded", object_id=str(p.pk)).after
    assert after["income_recorded"] is True and "3000" not in str(after)


def test_moving_away_from_self_employment_drops_the_details(officer, youth, enrollment):  # noqa: F811
    c = client_for(officer)
    pid = create(c, youth).json()["id"]
    r = c.patch(f"{PL}/{pid}", {"pathway": "wage"}, content_type=JSON)
    assert r.status_code == 200, r.content
    assert r.json()["business_activity"] == "" and r.json()["operational_status"] == ""
    before = AuditEvent.objects.get(action="placement.updated", object_id=pid).before
    assert before["business_activity"] == "Tailoring and repairs"  # kept in the trail


def test_unknown_operational_status_is_refused(enrollment):  # noqa: F811
    with pytest.raises(placements.PlacementError):
        placements.record_manual(
            actor=None, enrollment_id=enrollment.pk, pathway="self_employment",
            start_date=date(2026, 1, 1), operational_status="thriving",
        )  # fmt: skip


def test_options_offer_the_provisional_status_list(officer):  # noqa: F811
    body = client_for(officer).get(f"{PL}/options").json()
    assert [s["value"] for s in body["operational_statuses"]] == [
        "operating", "not_operating", "closed",
    ]  # fmt: skip
    assert body["operational_statuses_provisional"] is True
    assert body["can_record_income"] is False


def test_summary_counts_self_employment_apart_from_wage(officer, youth, enrollment):  # noqa: F811
    create(client_for(officer), youth)
    by = client_for(officer).get(f"{PL}/summary").json()["by_pathway"]
    assert by["self_employment"]["current"] == 1 and by["wage"]["current"] == 0
