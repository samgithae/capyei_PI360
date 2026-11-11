"""Draft rule versions for product owner review (T-048). Synthetic data only.

Acceptance: draft versions exist for the three modules, and every parameter is clearly marked
as waiting for a decision, so none of them can be approved by accident."""

from datetime import date

import pytest
from django.core.management import call_command

import pi360_rules
from apps.audit.models import AuditEvent
from apps.intelligence import initial_rules, services
from apps.intelligence.models import RuleSet, RuleVersion
from apps.intelligence.services import RuleViolation

SPECS = {spec["code"]: spec for spec in initial_rules.INITIAL}


@pytest.mark.parametrize("code", sorted(SPECS))
def test_each_draft_is_well_formed(code):
    assert pi360_rules.validate(SPECS[code]["definition"]) == []


@pytest.mark.parametrize("code", sorted(SPECS))
def test_no_number_is_invented(code):
    """Every parameter is empty, unapproved and names the decision that will set it; no factor
    carries a number of its own."""
    definition = SPECS[code]["definition"]
    for name, p in definition["parameters"].items():
        assert p["value"] is None, name
        assert p["approved"] is False, name
        assert p["decision"].startswith("D-"), name
        assert p["label"], name
    assert pi360_rules.unapproved(definition) == sorted(definition["parameters"])
    for f in definition["factors"]:
        assert isinstance(f["value"], dict) and set(f["value"]) <= {"param", "field"}, f["code"]
        assert not isinstance(f.get("weight"), (int, float)), f["code"]
        assert "max_age_days" not in f, f["code"]
        assert f.get("mandatory", False) is False, f["code"]  # classification is D-008


def test_one_rule_set_per_module():
    assert sorted(spec["module"] for spec in initial_rules.INITIAL) == ["A", "B", "C"]


@pytest.mark.django_db
def test_load_creates_drafts_once_and_audits_them():
    assert initial_rules.load() == sorted(SPECS, key=list(SPECS).index)
    assert initial_rules.load() == []  # safe to run again

    assert RuleSet.objects.count() == 3
    versions = RuleVersion.objects.select_related("rule_set")
    assert {(v.rule_set.code, v.number, v.status) for v in versions} == {
        (code, 1, RuleVersion.DRAFT) for code in SPECS
    }
    assert all(v.change_notes == initial_rules.CHANGE_NOTES for v in versions)
    assert AuditEvent.objects.filter(action="rule_version.created").count() == 3
    assert services.active_version("support-priority") is None  # nothing is in force


@pytest.mark.django_db
def test_load_leaves_an_existing_rule_set_alone(make_user):
    admin = make_user("amina", "Administrator")
    services.create_rule_set(
        actor=admin, module="A", code="support-priority", name="Edited by the rule owner"
    )
    assert "support-priority" not in initial_rules.load()
    assert RuleSet.objects.get(code="support-priority").name == "Edited by the rule owner"


@pytest.mark.django_db
def test_a_loaded_draft_cannot_be_approved_until_its_parameters_are_decided(make_user):
    admin = make_user("amina", "Administrator")
    initial_rules.load()
    version = RuleVersion.objects.get(rule_set__code="compatibility-default")
    services.submit(actor=admin, version=version)  # the shape is fine, so review can start
    with pytest.raises(RuleViolation) as blocked:
        services.approve(actor=admin, version=version)
    assert blocked.value.code == "unapproved_parameters"
    assert "w_skill" in blocked.value.message


@pytest.mark.django_db
def test_the_command_reports_what_it_created(capsys):
    call_command("load_initial_rules")
    assert "created 3 rule sets" in capsys.readouterr().out
    call_command("load_initial_rules")
    assert "created 0 rule sets: none" in capsys.readouterr().out


def test_a_weight_can_name_a_parameter():
    definition = {
        "factors": [
            {"code": "F1", "label": "Skill", "operator": "eq", "field": "x", "value": 1,
             "weight": {"param": "w_skill"}},
            {"code": "F2", "label": "Other", "operator": "eq", "field": "x", "value": 1,
             "weight": {"param": "missing"}},
        ],
        "parameters": {"w_skill": {"value": None, "approved": False}},
    }  # fmt: skip
    assert [p["path"] for p in pi360_rules.validate(definition)] == ["factors[1].weight"]

    checks = pi360_rules.evaluate(definition, {"x": 1}, date(2026, 11, 11))["checks"]
    assert checks[0]["weight"] is None  # undecided
    definition["parameters"]["w_skill"] = {"value": 3, "approved": True}
    checks = pi360_rules.evaluate(definition, {"x": 1}, date(2026, 11, 11))["checks"]
    assert checks[0]["weight"] == 3
