"""pi360_rules (T-047, CMP-08): the pure evaluator. No database, no Django.

Doc 07 §2.2: the same version and snapshot always give the same result.
Doc 07 §2.3: a check is pass, fail or unknown; unknown is never turned into fail."""

from datetime import date

import pytest

import pi360_rules
from pi360_rules import FAIL, PASS, UNKNOWN
from pi360_rules.operators import compare

TODAY = date(2026, 11, 11)


def factor(**over):
    base = {
        "code": "F1", "label": "A factor", "type": "test", "operator": "gte",
        "field": "x", "value": 5,
    }  # fmt: skip
    return {**base, **over}


@pytest.mark.parametrize(
    ("op", "actual", "expected", "outcome"),
    [
        ("eq", "Nairobi ", "nairobi", PASS),
        ("eq", "Kisumu", "nairobi", FAIL),
        ("in", "ict", ["ICT", "Retail"], PASS),
        ("in", "farming", ["ICT", "Retail"], FAIL),
        ("gte", 5, 5, PASS),
        ("gte", 4, 5, FAIL),
        ("gte", "2026-06-01", "2026-05-01", PASS),
        ("lte", 4, 5, PASS),
        ("lte", "2026-06-01", "2026-05-01", FAIL),
        ("between", 21, [18, 35], PASS),
        ("between", 40, [18, 35], FAIL),
        ("within_km", {"lat": -1.286, "lon": 36.817}, {"lat": -1.3, "lon": 36.8, "km": 10}, PASS),
        ("within_km", {"lat": -0.09, "lon": 34.77}, {"lat": -1.3, "lon": 36.8, "km": 10}, FAIL),
        ("overlaps", ["2026-01-01", "2026-03-01"], ["2026-02-01", "2026-04-01"], PASS),
        ("overlaps", ["2026-01-01", "2026-01-31"], ["2026-02-01", "2026-04-01"], FAIL),
        ("has_skill_level", {"excel": 3}, {"skill": "excel", "level": 2}, PASS),
        ("has_skill_level", {"word": 3}, {"skill": "excel", "level": 2}, FAIL),
        ("count_gte", ["a", "b", "c"], 3, PASS),
        ("count_gte", 2, 3, FAIL),
        ("days_since_gte", "2026-08-01", 90, PASS),
        ("days_since_gte", "2026-11-01", 90, FAIL),
    ],
)
def test_each_operator_passes_and_fails(op, actual, expected, outcome):
    assert compare(op, actual, expected, TODAY).outcome == outcome


def test_the_operator_set_is_the_fixed_list_from_the_spec():
    assert set(pi360_rules.OPERATORS) == {
        "eq", "in", "gte", "lte", "between", "within_km", "overlaps", "has_skill_level",
        "count_gte", "days_since_gte",
    }  # fmt: skip


@pytest.mark.parametrize(
    ("op", "actual", "expected"),
    [
        ("gte", None, 5),  # nothing recorded
        ("gte", "", 5),
        ("gte", 5, None),  # threshold not decided yet
        ("gte", "not a number", 5),  # cannot be compared
        ("gte", 5, "2026-01-01"),  # number against date
        ("between", 5, [1]),
        ("within_km", {"lat": 1}, {"lat": 1, "lon": 1, "km": 5}),
        ("days_since_gte", "yesterday", 3),
    ],
)
def test_missing_or_uncomparable_values_are_unknown_never_fail(op, actual, expected):
    check = compare(op, actual, expected, TODAY)
    assert check.outcome == UNKNOWN
    assert check.score is None
    assert check.note


def test_a_skill_below_the_level_fails_with_a_part_score():
    check = compare("has_skill_level", {"excel": 1}, {"skill": "excel", "level": 4}, TODAY)
    assert (check.outcome, check.score) == (FAIL, 0.25)


def test_evaluate_reports_each_factor_with_value_source_and_date():
    definition = {
        "factors": [
            factor(code="AGE", field="participant.age", operator="between", value=[18, 35]),
            factor(code="COUNTY", field="participant.county", operator="eq",
                   value={"field": "opportunity.county"}, mandatory=True),
            factor(code="GAP", field="participant.completed_on", operator="days_since_gte",
                   value={"param": "theta_time"}),
        ],
        "parameters": {"theta_time": {"value": None, "approved": False, "decision": "D-026"}},
    }  # fmt: skip
    snapshot = {
        "participant.age": {"value": 24, "source": "import", "verified": True,
                            "as_of": "2026-10-01"},
        "participant.county": "Nairobi",
        "opportunity.county": "nairobi",
        "participant.completed_on": "2026-06-30",
    }  # fmt: skip
    result = pi360_rules.evaluate(definition, snapshot, TODAY)
    by_code = {c["code"]: c for c in result["checks"]}
    assert by_code["AGE"]["outcome"] == PASS
    assert (by_code["AGE"]["source"], by_code["AGE"]["as_of"]) == ("import", "2026-10-01")
    assert by_code["COUNTY"]["outcome"] == PASS and by_code["COUNTY"]["mandatory"] is True
    # The threshold has no value yet (D-026): unknown, with a note that says why.
    assert by_code["GAP"]["outcome"] == UNKNOWN
    assert "theta_time" in by_code["GAP"]["note"]
    assert result["summary"] == {PASS: 2, FAIL: 0, UNKNOWN: 1}


def test_a_stale_value_is_unknown_when_the_rule_sets_a_maximum_age():
    definition = {"factors": [factor(max_age_days=90)]}
    fresh = {"x": {"value": 9, "as_of": "2026-10-01"}}
    stale = {"x": {"value": 9, "as_of": "2026-01-01"}}
    assert pi360_rules.evaluate(definition, fresh, TODAY)["checks"][0]["outcome"] == PASS
    check = pi360_rules.evaluate(definition, stale, TODAY)["checks"][0]
    assert check["outcome"] == UNKNOWN and "days old" in check["note"]


def test_evaluate_is_deterministic_and_does_not_change_its_inputs():
    definition = {"factors": [factor(), factor(code="F2", field="y", operator="eq", value="a")]}
    snapshot = {"x": 7, "y": "b"}
    before = (repr(definition), repr(snapshot))
    first = pi360_rules.evaluate(definition, snapshot, TODAY)
    assert pi360_rules.evaluate(definition, snapshot, TODAY) == first
    assert (repr(definition), repr(snapshot)) == before


def test_disabled_factors_are_skipped():
    definition = {"factors": [factor(), factor(code="F2", enabled=False)]}
    assert [c["code"] for c in pi360_rules.evaluate(definition, {"x": 9}, TODAY)["checks"]] == [
        "F1"
    ]


def test_a_module_evaluator_adds_its_own_reading_of_the_checks():
    @pi360_rules.evaluator("TEST")
    def _count(definition, checks, snapshot):
        return {"met": sum(1 for c in checks if c["outcome"] == PASS)}

    result = pi360_rules.evaluate({"factors": [factor()]}, {"x": 9}, TODAY, module="TEST")
    assert result["result"] == {"met": 1}


def test_validate_accepts_a_well_formed_definition():
    definition = {
        "factors": [factor(value={"param": "theta"}, weight=2, unknown_policy="flag")],
        "parameters": {"theta": {"label": "Threshold", "value": None, "approved": False}},
    }
    assert pi360_rules.validate(definition) == []
    assert pi360_rules.unapproved(definition) == ["theta"]


def test_validate_names_every_problem_with_its_path():
    definition = {
        "factors": [
            factor(operator="regex"),
            factor(weight=-1, unknown_policy="guess", value={"param": "missing"}),
            {"code": ""},
        ],
        "parameters": {"theta": {"value": None, "approved": True}},
        "extra": 1,
    }
    paths = {p["path"] for p in pi360_rules.validate(definition)}
    assert {
        "extra", "parameters.theta", "factors[0].operator", "factors[1].code",
        "factors[1].weight", "factors[1].unknown_policy", "factors[1].value",
        "factors[2].code", "factors[2].label", "factors[2].operator", "factors[2].field",
        "factors[2].value",
    } <= paths  # fmt: skip


def test_validate_refuses_a_definition_without_factors():
    assert pi360_rules.validate({"factors": []})[0]["path"] == "factors"
    assert pi360_rules.validate([])[0]["path"] == ""


def test_a_parameter_waits_only_while_it_has_no_value():
    definition = {
        "factors": [factor()],
        "parameters": {
            "a": {"value": 3, "approved": True},
            "b": {"value": 3, "approved": False},
            "c": {"value": None, "approved": False},
        },
    }
    assert pi360_rules.unapproved(definition) == ["c"]  # the approver signs off the rest
