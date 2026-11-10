import pytest
from django.test import Client
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.audit.models import AuditEvent
from apps.configuration import services
from apps.configuration.models import County, FeatureFlag, ReferenceAlias, ReferenceLabel, Ward
from apps.configuration.services import ConfigError

PW = "correct-horse-battery-9"


@pytest.fixture
def admin(make_user):
    u = make_user("admin", "Administrator")
    u.set_password(PW)
    u.save()
    return u


def api(user):
    c = Client()
    c.force_login(user)
    return c


def post(c, url, body):
    return c.post(url, body, content_type="application/json")


def patch(c, url, body):
    return c.patch(url, body, content_type="application/json")


def actions():
    return list(AuditEvent.objects.values_list("action", flat=True))


@pytest.mark.django_db
def test_forty_seven_counties_seeded_in_order():
    assert County.objects.count() == 47
    assert County.objects.get(code="47").name == "Nairobi"
    services.ensure_seed_data()  # idempotent
    assert County.objects.count() == 47


@pytest.mark.django_db
def test_counties_cannot_be_added(admin):
    r = post(api(admin), "/api/v1/config/reference/counties", {"code": "48", "name": "X"})
    assert r.status_code == 400


@pytest.mark.django_db
def test_reference_lifecycle_is_audited_and_never_deletes(admin):
    c = api(admin)
    r = post(c, "/api/v1/config/reference/sectors", {"code": "ICT", "name": "ICT"})
    assert r.status_code == 201
    pk = r.json()["id"]
    assert (
        patch(c, f"/api/v1/config/reference/sectors/{pk}", {"code": "X"}).status_code == 400
    )  # code is stable
    assert (
        patch(c, f"/api/v1/config/reference/sectors/{pk}", {"name": "Digital"}).status_code == 200
    )
    assert [x.name for x in ReferenceLabel.objects.order_by("valid_from")] == ["ICT", "Digital"]
    assert (
        post(c, f"/api/v1/config/reference/sectors/{pk}/deactivate", {}).json()["active"] is False
    )
    assert post(c, f"/api/v1/config/reference/sectors/{pk}/reactivate", {}).json()["active"] is True
    assert {
        "reference.created",
        "reference.changed",
        "reference.deactivated",
        "reference.reactivated",
    } <= set(actions())


@pytest.mark.django_db
def test_duplicate_name_variants_rejected(admin):
    c = api(admin)
    post(c, "/api/v1/config/reference/sectors", {"code": "A", "name": "Hospitality"})
    r = post(c, "/api/v1/config/reference/sectors", {"code": "B", "name": " hospitality! "})
    assert r.status_code == 400


@pytest.mark.django_db
def test_same_ward_name_under_two_sub_counties(admin):
    c = api(admin)
    county = County.objects.get(code="01")
    subs = []
    for code in ("S1", "S2"):
        r = post(
            c,
            "/api/v1/config/reference/sub-counties",
            {"code": code, "name": f"Sub {code}", "county": str(county.pk)},
        )
        assert r.status_code == 201, r.json()
        subs.append(r.json()["id"])
    for i, s in enumerate(subs):
        r = post(
            c,
            "/api/v1/config/reference/wards",
            {"code": f"W{i}", "name": "Central", "sub_county": s},
        )
        assert r.status_code == 201, r.json()
    dup = post(
        c,
        "/api/v1/config/reference/wards",
        {"code": "W9", "name": "central", "sub_county": subs[0]},
    )
    assert dup.status_code == 400
    assert Ward.objects.count() == 2


@pytest.mark.django_db
def test_alias_resolves_source_spelling(admin):
    c = api(admin)
    pk = post(c, "/api/v1/config/reference/sectors", {"code": "ICT", "name": "ICT"}).json()["id"]
    assert (
        post(
            c, f"/api/v1/config/reference/sectors/{pk}/aliases", {"alias": "I.C.T Services"}
        ).status_code
        == 201
    )
    assert str(services.resolve("sectors", "i c t services").pk) == pk
    assert services.resolve("sectors", "unknown") is None
    assert (
        post(
            c, f"/api/v1/config/reference/sectors/{pk}/aliases", {"alias": "i.c.t  services!"}
        ).status_code
        == 400
    )
    assert ReferenceAlias.objects.count() == 1


@pytest.mark.django_db
def test_unknown_kind_and_bad_parent(admin):
    c = api(admin)
    assert c.get("/api/v1/config/reference/nope").status_code == 404
    r = post(
        c, "/api/v1/config/reference/wards", {"code": "W", "name": "W", "sub_county": "garbage"}
    )
    assert r.status_code == 400


@pytest.mark.django_db
def test_flag_off_by_default_and_audience(admin, make_user):
    assert services.is_enabled("new.screen", admin) is False
    c = api(admin)
    assert (
        patch(
            c, "/api/v1/config/flags/new.screen", {"enabled": True, "reason": "pilot"}
        ).status_code
        == 200
    )
    assert services.is_enabled("new.screen", admin) is True
    patch(c, "/api/v1/config/flags/new.screen", {"roles": ["Data steward"]})
    assert services.is_enabled("new.screen", admin) is False
    assert services.is_enabled("new.screen", make_user("ds", "Data steward")) is True
    patch(c, "/api/v1/config/flags/new.screen", {"roles": [], "environments": ["production"]})
    assert services.is_enabled("new.screen", admin) is False  # APP_ENV is development in tests
    assert "flag.changed" in actions()
    assert FeatureFlag.objects.count() == 1


@pytest.mark.django_db
def test_flag_gate_hides_route(rf, admin):
    from django.http import Http404

    from apps.configuration.flags import FlagGate

    class V:
        required_flag = "x.y"

    req = rf.get("/")
    req.user = admin
    with pytest.raises(Http404):
        FlagGate().has_permission(req, V())
    services.set_flag(actor=admin, key="x.y", enabled=True)
    assert FlagGate().has_permission(req, V()) is True


def change(c, **over):
    body = {"key": "import.max_upload_mb", "value": 50, "reason": "bigger files", "password": PW}
    body.update(over)
    return post(c, "/api/v1/config/settings", body)


@pytest.mark.django_db
def test_protected_setting_step_up(admin):
    c = api(admin)
    assert change(c, password="wrong").status_code == 400
    assert "auth.step_up_failed" in actions()
    assert change(c, reason=" ").status_code == 400
    assert change(c, value=0).status_code == 400
    assert change(c, key="nope").status_code == 400
    assert services.get_setting("import.max_upload_mb") == 20
    assert change(c).status_code == 204
    assert services.get_setting("import.max_upload_mb") == 50
    ev = AuditEvent.objects.get(action="setting.changed")
    assert ev.reason == "bigger files"


@pytest.mark.django_db
def test_protected_setting_needs_totp_when_enrolled(admin):
    TOTPDevice.objects.create(user=admin, name="d", confirmed=True)
    c = api(admin)
    assert change(c).status_code == 400  # password alone is not enough
    assert change(c, code="000000").status_code == 400


@pytest.mark.django_db
def test_steward_cannot_change_protected_settings(make_user):
    c = api(make_user("ds", "Data steward"))
    assert change(c).status_code == 403
    with pytest.raises(ConfigError):
        services.change_setting(actor=make_user("x"), key="nope", value=1, reason="r", password="p")
