"""T-087 stage B: employer name clustering is a suggestion; stewards decide; decisions reverse."""

import pytest

from apps.audit.models import AuditEvent
from apps.employers import services as emp
from apps.employers.models import Employer, EmployerAlias


def test_key_ignores_case_punctuation_and_legal_suffixes():
    keys = {emp.cluster_key(n) for n in ("ACME Ltd.", "Acme Limited", "acme  co", "Acme")}
    assert keys == {"acme"}
    assert emp.cluster_key("Limited") == "limited"  # never reduced to nothing
    assert emp.cluster_key("Acme Ltd") != emp.cluster_key("Acme Foods Ltd")


def test_build_clusters_groups_counts_and_suggests(db):
    Employer.objects.create(name="Acme Limited")
    c = emp.build_clusters(["Acme Ltd", "ACME LTD", "Acme Ltd", "Beta Works", "", None])
    assert [x["key"] for x in c] == ["acme", "beta works"]
    assert c[0]["count"] == 3 and c[0]["spellings"][0] == {"text": "Acme Ltd", "count": 2}
    assert [s["name"] for s in c[0]["suggested"]] == ["Acme Limited"]
    assert c[1]["suggested"] == []
    assert Employer.objects.count() == 1  # grouping changed nothing


def test_link_creates_aliases_and_resolves(db, make_user):
    steward = make_user("stew", "Data steward")
    e = Employer.objects.create(name="Acme Limited")
    d = emp.decide_cluster(
        actor=steward, key="acme", spellings=["Acme Ltd", "ACME LTD"], action="link",
        employer_id=e.pk,
    )  # fmt: skip
    assert emp.resolve_name("Acme Ltd ") == e.pk and emp.resolve_name("Other") is None
    assert d.aliases.count() == 2 and Employer.objects.count() == 1
    assert AuditEvent.objects.filter(action="employer.cluster_decided").exists()


def test_create_and_apart(db, make_user):
    steward = make_user("stew", "Data steward")
    emp.decide_cluster(actor=steward, key="a", spellings=["Acme Ltd", "ACME"], action="create")
    assert Employer.objects.count() == 1 and EmployerAlias.objects.count() == 2
    emp.decide_cluster(actor=steward, key="b", spellings=["Beta A", "Beta B"], action="apart")
    assert Employer.objects.count() == 3


def test_spelling_cannot_be_linked_twice_and_failure_rolls_back(db, make_user):
    steward = make_user("stew", "Data steward")
    emp.decide_cluster(actor=steward, key="a", spellings=["Acme Ltd"], action="create")
    with pytest.raises(emp.ClusterError):
        emp.decide_cluster(
            actor=steward, key="a", spellings=["New One", "Acme Ltd"], action="create"
        )
    assert (
        Employer.objects.count() == 1
        and not EmployerAlias.objects.filter(source_name="New One").exists()
    )


def test_link_needs_a_real_employer(db, make_user):
    with pytest.raises(emp.ClusterError):
        emp.decide_cluster(actor=make_user("s", "Data steward"), key="a", spellings=["X"],
                           action="link", employer_id=None)  # fmt: skip


def test_reverse_removes_aliases_and_created_employers(db, make_user):
    steward = make_user("stew", "Data steward")
    existing = Employer.objects.create(name="Keep Me")
    linked = emp.decide_cluster(
        actor=steward, key="k", spellings=["Keep Me Ltd"], action="link", employer_id=existing.pk
    )
    made = emp.decide_cluster(actor=steward, key="a", spellings=["Acme Ltd"], action="create")
    emp.reverse_decision(actor=steward, decision=linked)
    emp.reverse_decision(actor=steward, decision=made)
    assert list(Employer.objects.all()) == [existing]  # a linked employer is never deleted
    assert EmployerAlias.objects.count() == 0 and emp.resolve_name("Acme Ltd") is None
    with pytest.raises(emp.ClusterError):
        emp.reverse_decision(actor=steward, decision=made)


def test_reverse_refused_when_employer_is_in_use(db, make_user):
    steward = make_user("stew", "Data steward")
    d = emp.decide_cluster(actor=steward, key="a", spellings=["Acme Ltd"], action="create")
    employer = Employer.objects.get(pk=d.created_employers[0])
    emp.create_opportunity(
        actor=steward, employer=employer, data={"title": "Welder", "kind": "job"}
    )
    with pytest.raises(emp.ClusterError):
        emp.reverse_decision(actor=steward, decision=d)
    assert Employer.objects.filter(pk=employer.pk).exists() and d.aliases.count() == 1
