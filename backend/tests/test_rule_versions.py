"""Rule sets and versions (T-047, doc 07 §2.4). Synthetic data only.

Acceptance: the active version is immutable; activation is audited."""

import copy
from datetime import date

import pytest
from django.test import Client

from apps.audit.models import AuditEvent
from apps.identity import services as identity
from apps.identity.models import Role
from apps.intelligence import services
from apps.intelligence.models import Immutable, RuleSet, RuleVersion

URL = "/api/v1/rules"
JSON = "application/json"
DEFINITION = {
    "factors": [
        {"code": "A-TIME", "label": "Time without transition", "type": "time",
         "operator": "days_since_gte", "field": "participant.completed_on",
         "value": {"param": "theta_time"}},
    ],
    "parameters": {"theta_time": {"label": "Days", "value": 90, "approved": True}},
}  # fmt: skip


@pytest.fixture
def admin(make_user):
    return make_user("amina", "Administrator")


@pytest.fixture
def drafter(make_user):
    """Someone who may draft rules but not approve them (a second pair of eyes is needed)."""
    role = Role.objects.create(
        name="Rule owner", permissions=["intelligence.view", "intelligence.manage_rules"]
    )
    user = make_user("otieno", "M&E analyst")
    identity.assign_role(actor=None, user=user, role=role)
    return user


@pytest.fixture
def rule_set(admin):
    return services.create_rule_set(
        actor=admin, module="A", code="support-priority", name="Support priority",
        definition=copy.deepcopy(DEFINITION),
    )  # fmt: skip


def draft_of(rule_set):
    return rule_set.versions.get(status=RuleVersion.DRAFT)


def go_live(admin, version):
    services.submit(actor=admin, version=version)
    services.approve(actor=admin, version=version)
    return services.activate(actor=admin, version=version, note="Agreed at the workshop")


def client_for(user):
    c = Client()
    c.force_login(user)
    return c


def actions_of(version):
    return list(
        AuditEvent.objects.filter(object_type="rule_version", object_id=str(version.pk))
        .order_by("pk").values_list("action", flat=True)
    )  # fmt: skip


def test_a_new_rule_set_starts_with_version_one_as_a_draft(rule_set):
    v = draft_of(rule_set)
    assert (v.number, v.status) == (1, RuleVersion.DRAFT)
    assert services.active_version("support-priority") is None
    assert actions_of(v) == ["rule_version.created"]


def test_a_draft_can_be_edited_and_the_edit_is_audited(admin, rule_set):
    v = draft_of(rule_set)
    changed = copy.deepcopy(DEFINITION)
    changed["parameters"]["theta_time"]["value"] = 120
    services.update_draft(actor=admin, version=v, definition=changed)
    v.refresh_from_db()
    assert v.definition["parameters"]["theta_time"]["value"] == 120
    event = AuditEvent.objects.filter(action="rule_version.edited").get()
    assert event.after["changes"]["parameters_changed"]["theta_time"] == {
        "from": {"value": 90, "approved": True},
        "to": {"value": 120, "approved": True},
    }
    assert event.before["definition_hash"] != event.after["definition_hash"]
    assert "definition" not in event.after  # the fingerprint, not the whole definition


def test_a_draft_with_a_broken_definition_cannot_be_sent_for_review(admin, rule_set):
    v = draft_of(rule_set)
    services.update_draft(actor=admin, version=v, definition={"factors": []})
    with pytest.raises(services.RuleViolation) as exc:
        services.submit(actor=admin, version=v)
    assert exc.value.code == "invalid_definition"


def test_a_version_with_an_undecided_parameter_cannot_be_approved(admin, rule_set):
    v = draft_of(rule_set)
    waiting = copy.deepcopy(DEFINITION)
    waiting["parameters"]["theta_time"] = {"value": None, "approved": False, "decision": "D-026"}
    services.update_draft(actor=admin, version=v, definition=waiting)
    services.submit(actor=admin, version=v)  # review may start while values are open
    with pytest.raises(services.RuleViolation) as exc:
        services.approve(actor=admin, version=v)
    assert exc.value.code == "unapproved_parameters"
    assert "theta_time" in exc.value.message


def test_activation_is_audited_with_who_when_and_what(admin, rule_set):
    v = go_live(admin, draft_of(rule_set))
    assert v.status == RuleVersion.ACTIVE and v.effective_from is not None
    assert services.active_version("support-priority").pk == v.pk
    event = AuditEvent.objects.get(action="rule_version.activated", object_id=str(v.pk))
    assert event.actor_label == "amina"
    assert event.reason == "Agreed at the workshop"
    assert (event.before["status"], event.after["status"]) == ("approved", "active")
    assert event.after["rule_set"] == "support-priority" and event.after["number"] == 1
    assert event.after["definition_hash"] == services.definition_hash(v.definition)
    assert actions_of(v) == [
        "rule_version.created", "rule_version.submitted", "rule_version.approved",
        "rule_version.activated",
    ]  # fmt: skip


def test_the_active_version_cannot_be_edited(admin, rule_set):
    v = go_live(admin, draft_of(rule_set))
    with pytest.raises(services.RuleViolation) as exc:
        services.update_draft(actor=admin, version=v, definition={"factors": []})
    assert exc.value.code == "wrong_status"
    # The model refuses too, whatever code path tries it.
    v.refresh_from_db()
    v.definition = {"factors": []}
    with pytest.raises(Immutable):
        v.save()
    with pytest.raises(Immutable):
        RuleVersion.objects.filter(pk=v.pk).update(definition={})
    with pytest.raises(Immutable):
        RuleVersion.objects.filter(pk=v.pk).delete()
    v.refresh_from_db()
    with pytest.raises(Immutable):
        v.delete()
    assert v.definition == DEFINITION


def test_a_version_that_has_been_active_never_becomes_a_draft_again(admin, rule_set):
    v = go_live(admin, draft_of(rule_set))
    v.status = RuleVersion.DRAFT
    with pytest.raises(Immutable):
        v.save()
    with pytest.raises(Immutable):
        RuleVersion.objects.filter(pk=v.pk).update(status=RuleVersion.DRAFT)
    with pytest.raises(services.RuleViolation):
        services.send_back(actor=admin, version=v, note="reopen")


def test_a_change_is_a_new_version_and_activating_it_retires_the_old_one(admin, rule_set):
    v1 = go_live(admin, draft_of(rule_set))
    v2 = services.clone(actor=admin, version=v1, change_notes="Raise the threshold")
    assert (v2.number, v2.status, v2.cloned_from_id) == (2, RuleVersion.DRAFT, v1.pk)
    changed = copy.deepcopy(v2.definition)
    changed["parameters"]["theta_time"]["value"] = 120
    services.update_draft(actor=admin, version=v2, definition=changed)
    go_live(admin, v2)
    v1.refresh_from_db()
    assert v1.status == RuleVersion.RETIRED and v1.retired_at is not None
    assert v1.definition == DEFINITION  # the old version still says what it said
    assert services.active_version("support-priority").number == 2
    assert RuleVersion.objects.filter(rule_set=rule_set, status=RuleVersion.ACTIVE).count() == 1
    assert "rule_version.retired" in actions_of(v1)


def test_emergency_deactivation_falls_back_to_the_previous_version(admin, rule_set):
    v1 = go_live(admin, draft_of(rule_set))
    v2 = go_live(admin, services.clone(actor=admin, version=v1))
    with pytest.raises(services.RuleViolation) as exc:
        services.deactivate(actor=admin, version=v2, reason=" ")
    assert exc.value.code == "reason_required"
    back = services.deactivate(actor=admin, version=v2, reason="Wrong threshold went live")
    assert back.pk == v1.pk
    v1.refresh_from_db(), v2.refresh_from_db()
    assert (v1.status, v2.status) == (RuleVersion.ACTIVE, RuleVersion.RETIRED)
    event = AuditEvent.objects.get(action="rule_version.deactivated")
    assert event.reason == "Wrong threshold went live" and event.after["fallback"] == 1
    assert AuditEvent.objects.filter(
        action="rule_version.reactivated", object_id=str(v1.pk)
    ).exists()


def test_deactivating_the_only_version_leaves_the_rule_set_without_one(admin, rule_set):
    v1 = go_live(admin, draft_of(rule_set))
    assert services.deactivate(actor=admin, version=v1, reason="Stop") is None
    assert services.active_version("support-priority") is None
    assert services.evaluate("support-priority", {}, date(2026, 11, 11)) is None


def test_returning_a_version_needs_a_note_and_reopens_it_for_editing(admin, rule_set):
    v = draft_of(rule_set)
    services.submit(actor=admin, version=v)
    with pytest.raises(services.RuleViolation):
        services.send_back(actor=admin, version=v, note="")
    services.send_back(actor=admin, version=v, note="Weights need another look")
    v.refresh_from_db()
    assert v.status == RuleVersion.DRAFT
    services.update_draft(actor=admin, version=v, change_notes="Looked again")


def test_only_a_draft_can_be_discarded(admin, rule_set):
    v1 = go_live(admin, draft_of(rule_set))
    with pytest.raises(services.RuleViolation):
        services.discard(actor=admin, version=v1)
    v2 = services.clone(actor=admin, version=v1)
    services.discard(actor=admin, version=v2)
    assert not RuleVersion.objects.filter(pk=v2.pk).exists()
    assert AuditEvent.objects.filter(action="rule_version.discarded").exists()


def test_evaluate_uses_the_active_version_and_names_it(admin, rule_set):
    v = go_live(admin, draft_of(rule_set))
    result = services.evaluate(
        "support-priority", {"participant.completed_on": "2026-06-30"}, date(2026, 11, 11)
    )
    assert (result["version_id"], result["version"]) == (str(v.pk), 1)
    assert result["checks"][0]["outcome"] == "pass"
    services.mark_used(v)
    v.refresh_from_db()
    assert v.used_at is not None


# ---- API -------------------------------------------------------------------------------------


def test_api_full_lifecycle(admin):
    c = client_for(admin)
    created = c.post(
        URL, {"module": "B", "code": "compatibility-default", "name": "Compatibility"}, JSON
    )
    assert created.status_code == 201, created.content
    vid = created.json()["versions"][0]["id"]
    v = f"{URL}/versions/{vid}"

    detail = c.get(v).json()
    assert detail["status"] == "draft"
    assert set(detail["actions"]) == {"edit", "submit", "discard", "clone"}
    assert detail["problems"]  # an empty definition has no factors yet

    assert c.post(f"{v}/submit", {}, JSON).status_code == 409
    assert c.patch(v, {"definition": DEFINITION, "change_notes": "First"}, JSON).status_code == 200
    assert c.get(v).json()["problems"] == []
    assert c.post(f"{v}/submit", {}, JSON).json()["status"] == "in_review"
    assert c.post(f"{v}/approve", {}, JSON).json()["status"] == "approved"
    live = c.post(f"{v}/activate", {"note": "Go"}, JSON).json()
    assert live["status"] == "active" and live["actions"] == ["clone", "deactivate"]

    assert c.patch(v, {"definition": {"factors": []}}, JSON).status_code == 409
    assert c.delete(v).status_code == 409

    listed = c.get(URL).json()
    assert listed[0]["active"]["number"] == 1 and listed[0]["version_count"] == 1
    assert [e["action"] for e in c.get(f"{v}/history").json()][0] == "rule_version.activated"
    assert {o["code"] for o in c.get(f"{URL}/operators").json()} >= {"eq", "within_km"}

    copy_ = c.post(f"{v}/clone", {"note": "Next round"}, JSON).json()
    assert (copy_["number"], copy_["status"], copy_["cloned_from"]) == (2, "draft", 1)
    assert len(c.get(f"{URL}/{created.json()['id']}").json()["versions"]) == 2
    assert c.delete(f"{URL}/versions/{copy_['id']}").status_code == 204


def test_api_a_drafter_cannot_approve_or_activate(admin, drafter, rule_set):
    v = draft_of(rule_set)
    c = client_for(drafter)
    base = f"{URL}/versions/{v.pk}"
    detail = c.get(base).json()
    assert set(detail["actions"]) == {"edit", "submit", "discard", "clone"}
    assert c.post(f"{base}/submit", {}, JSON).status_code == 200
    for step in ("approve", "activate", "return", "deactivate"):
        assert c.post(f"{base}/{step}", {}, JSON).status_code == 403, step
    assert c.get(base).json()["actions"] == ["clone"]
    assert client_for(admin).post(f"{base}/approve", {}, JSON).status_code == 200


def test_api_viewers_can_read_rules_but_not_change_them(make_user, rule_set):
    c = client_for(make_user("wanjiru", "Placement officer"))
    assert c.get(URL).status_code == 200
    v = draft_of(rule_set)
    assert c.get(f"{URL}/versions/{v.pk}").json()["actions"] == []
    assert c.patch(f"{URL}/versions/{v.pk}", {"change_notes": "x"}, JSON).status_code == 403
    assert c.post(URL, {"module": "A", "code": "x", "name": "X"}, JSON).status_code == 403


def test_api_duplicate_code_is_refused(admin, rule_set):
    r = client_for(admin).post(
        URL, {"module": "A", "code": "support-priority", "name": "Again"}, JSON
    )
    assert r.status_code == 409 and r.json()["errors"][0]["code"] == "duplicate_code"


def test_the_shipped_administrator_role_gets_the_rule_permissions(db):
    identity.ensure_default_roles()
    perms = Role.objects.get(name="Administrator").permissions
    assert {"intelligence.manage_rules", "intelligence.approve_rules"} <= set(perms)
    assert RuleSet.objects.count() == 0
