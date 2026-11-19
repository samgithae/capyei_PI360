"""Data retention (T-073): nothing is reduced without a period AND an approval, a dry run
changes nothing, and what reconciliation and re-upload checks need survives reduction."""

from datetime import timedelta

import pytest
from django.core.management import call_command
from django.test import Client
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.imports import services as imports
from apps.imports.models import ImportRow, RecordLineage
from apps.retention import services
from apps.retention.models import RetentionRun

from .test_imports import GOOD, SIGN, load, steward, template, upload, world  # noqa: F401

CLASS = "import_rows"


@pytest.fixture
def admin(make_user):
    return make_user("admin1", "Administrator")


@pytest.fixture
def signed(template, steward):  # noqa: F811
    b = load(steward, upload(steward, template, *GOOD))
    imports.sign_off(actor=steward, batch=b, **SIGN)
    return b


def far_future():
    return timezone.now() + timedelta(days=400)


def approved(admin, days=365):
    services.set_period(actor=admin, data_class=CLASS, period_days=days, basis="Policy 4.2")
    services.approve(actor=admin, data_class=CLASS)


@pytest.mark.django_db
def test_nothing_happens_without_a_period_or_approval(admin, signed):
    r = services.run(actor=admin, apply=True, now=far_future())
    assert r["results"][CLASS] == {"skipped": "no period set"}
    services.set_period(actor=admin, data_class=CLASS, period_days=365, basis="Policy 4.2")
    r = services.run(actor=admin, apply=True, now=far_future())
    assert r["results"][CLASS]["skipped"] == "not approved"
    assert r["results"][CLASS]["eligible"]["rows"] == 3  # counted, not touched
    assert not ImportRow.objects.filter(reduced_at__isnull=False).exists()


@pytest.mark.django_db
def test_changing_the_period_withdraws_the_approval(admin):
    approved(admin)
    assert services.overview()["classes"][0]["state"] == "active"
    services.set_period(actor=admin, data_class=CLASS, period_days=400, basis="Policy 4.2")
    assert services.overview()["classes"][0]["state"] == "awaiting_approval"
    assert AuditEvent.objects.filter(action="retention.period_set").count() == 2


@pytest.mark.django_db
def test_period_rules(admin):
    with pytest.raises(services.RetentionError) as e:
        services.set_period(actor=admin, data_class=CLASS, period_days=5, basis="x")
    assert e.value.code == "too_short"
    with pytest.raises(services.RetentionError) as e:
        services.set_period(actor=admin, data_class=CLASS, period_days=365, basis=" ")
    assert e.value.field == "basis"
    with pytest.raises(services.RetentionError) as e:
        services.approve(actor=admin, data_class=CLASS)  # nothing set yet
    assert e.value.code == "required"
    with pytest.raises(services.RetentionError) as e:
        services.set_period(actor=admin, data_class="nope", period_days=365, basis="x")
    assert e.value.code == "not_found"


@pytest.mark.django_db
def test_revoke_needs_reason_and_stops_reduction(admin, signed):
    approved(admin)
    with pytest.raises(services.RetentionError):
        services.revoke(actor=admin, data_class=CLASS, reason=" ")
    services.revoke(actor=admin, data_class=CLASS, reason="Policy under review")
    r = services.run(actor=admin, apply=True, now=far_future())
    assert r["results"][CLASS]["skipped"] == "not approved"


@pytest.mark.django_db
def test_dry_run_changes_nothing_but_is_recorded(admin, signed):
    approved(admin)
    r = services.run(actor=admin, apply=False, now=far_future())
    assert r["applied"] is False and r["results"][CLASS]["eligible"]["rows"] == 3
    assert not ImportRow.objects.filter(reduced_at__isnull=False).exists()
    assert RetentionRun.objects.count() == 1
    assert AuditEvent.objects.filter(action="retention.dry_run").count() == 1


@pytest.mark.django_db
def test_applied_run_clears_values_and_keeps_what_is_needed(admin, signed):
    before = imports.reconciliation(signed)
    hashes = set(ImportRow.objects.values_list("row_hash", flat=True))
    approved(admin)
    r = services.run(actor=admin, apply=True, now=far_future())
    assert r["results"][CLASS]["reduced"] == {"rows": 3}
    rows = ImportRow.objects.all()
    assert all(x.raw == {} and x.diff == [] and x.reduced_at for x in rows)
    assert all(set(x.clean) <= {"cohort_code"} for x in rows)
    assert set(rows.values_list("row_hash", flat=True)) == hashes
    assert not any(l.before or l.after for l in RecordLineage.objects.all())  # noqa: E741
    after = imports.reconciliation(signed)
    assert after["balanced"] and after["controls_match"]
    assert after["controls"] == before["controls"]
    ev = AuditEvent.objects.get(action="retention.run")
    assert "Test One" not in str(ev.after)  # counts only
    # Running again finds nothing left.
    again = services.run(actor=admin, apply=True, now=far_future())
    assert again["results"][CLASS]["reduced"] == {"rows": 0}


@pytest.mark.django_db
def test_unsigned_or_recent_batches_are_untouched(admin, template, steward):  # noqa: F811
    load(steward, upload(steward, template, *GOOD))  # loaded, never signed off
    approved(admin)
    r = services.run(actor=admin, apply=True, now=far_future())
    assert r["results"][CLASS]["reduced"] == {"rows": 0}
    b = load(steward, upload(steward, template, "New P,P1,K1,C1,E-099,F,20,01"))
    imports.sign_off(actor=steward, batch=b, **SIGN)
    r = services.run(actor=admin, apply=True)  # signed today, 365-day period: not yet due
    assert r["results"][CLASS]["reduced"] == {"rows": 0}


@pytest.mark.django_db
def test_recheck_is_refused_after_reduction(admin, signed, steward):  # noqa: F811
    approved(admin)
    services.run(actor=admin, apply=True, now=far_future())
    with pytest.raises(imports.ImportFailure):
        imports.recheck(actor=steward, batch=signed)


@pytest.mark.django_db
def test_management_command_is_dry_by_default(admin, signed, capsys):
    approved(admin, days=30)
    call_command("run_retention")
    assert "DRY RUN" in capsys.readouterr().out
    assert not ImportRow.objects.filter(reduced_at__isnull=False).exists()
    RetentionRun.objects.all().delete()
    from apps.imports.models import ReconciliationSignoff

    ReconciliationSignoff.objects.update(created_at=timezone.now() - timedelta(days=60))
    call_command("run_retention", "--apply")
    assert "APPLIED" in capsys.readouterr().out
    assert ImportRow.objects.filter(reduced_at__isnull=False).count() == 3
    assert RetentionRun.objects.get().actor_label == "system"


@pytest.mark.django_db
def test_api_flow_and_permissions(admin, steward, signed):  # noqa: F811
    c = Client()
    c.force_login(steward)
    assert c.get("/api/v1/retention").status_code == 403
    c.force_login(admin)
    assert c.get("/api/v1/retention").json()["classes"][0]["state"] == "not_set"
    put = c.put(
        f"/api/v1/retention/{CLASS}",
        {"period_days": 365, "basis": "Policy 4.2"},
        content_type="application/json",
    )
    assert put.status_code == 200 and put.json()["classes"][0]["state"] == "awaiting_approval"
    short = c.put(
        f"/api/v1/retention/{CLASS}",
        {"period_days": 3, "basis": "x"},
        content_type="application/json",
    )
    assert short.status_code == 409 and short.json()["errors"][0]["code"] == "too_short"
    assert c.post(f"/api/v1/retention/{CLASS}/approve").status_code == 200
    assert c.post("/api/v1/retention/nope/approve").status_code == 404
    dry = c.post("/api/v1/retention/run", {}, content_type="application/json")
    assert dry.status_code == 200 and dry.json()["applied"] is False
    nope = c.post("/api/v1/retention/run", {"apply": True}, content_type="application/json")
    assert nope.status_code == 409 and nope.json()["errors"][0]["code"] == "confirm_required"
    ok = c.post(
        "/api/v1/retention/run", {"apply": True, "confirm": True}, content_type="application/json"
    )
    assert ok.status_code == 200 and ok.json()["applied"] is True
    rev = c.post(
        f"/api/v1/retention/{CLASS}/revoke", {"reason": "pause"}, content_type="application/json"
    )
    assert rev.status_code == 200 and rev.json()["classes"][0]["state"] == "awaiting_approval"
