"""Project isolation (Epic L: NEW-056, 059, 060, 061). All data here is synthetic.

Two projects and one youth enrolled in both. A Project officer sees the youth in their own
projects (a shared youth is visible to both officers), never one in another project, never one
with no project, and has no access at all while nothing is assigned (D-085)."""

import pytest
from django.test import Client

from apps.identity import services as identity
from apps.identity.defaults import DEFAULT_ROLES
from apps.identity.models import Role
from apps.imports import services as imports
from apps.participants import services as participants
from apps.participants.models import Participant

from .test_participants import enrol, world  # noqa: F401


def client(user):
    c = Client()
    c.force_login(user)
    return c


@pytest.fixture
def people(world):  # noqa: F811
    """one, two: each in one project. shared: in both. orphan: in none."""
    out = {n: Participant.objects.create(full_name_source=f"Synthetic {n}") for n in
           ("one", "two", "shared", "orphan")}  # fmt: skip
    enrol(world, out["one"], 0, "A1")
    enrol(world, out["two"], 1, "B1")
    enrol(world, out["shared"], 0, "A2")
    enrol(world, out["shared"], 1, "B2")
    return out


def officer(make_user, name, *projects):
    user = make_user(name, "Project officer")
    identity.set_scopes(actor=None, user=user, scopes=[("project", str(p.pk)) for p in projects])
    return user


def ids(user):
    return {str(i) for i in participants.visible_ids(user).values_list("pk", flat=True)}


def names(response):
    return {r["name"] for r in response.json()["results"]}


# --- NEW-056: the role ---------------------------------------------------------------------


def test_the_role_is_a_placement_officer_limited_to_assigned_scope(db, make_user):
    by = {r["name"]: r for r in DEFAULT_ROLES}
    role = Role.objects.get(name="Project officer")
    assert role.scope_mode == "assigned" and role.active and role.is_system
    assert set(role.permissions) == set(by["Placement officer"]["permissions"])
    assert "ydm.assess" not in role.permissions  # B14/B16: not for Project officers
    assert not any(p.startswith("exports.identifiable") for p in role.permissions)  # C-2: a grant


def test_shipping_the_role_leaves_existing_roles_alone(db):
    po = Role.objects.get(name="Placement officer")
    po.permissions = ["participants.view"]
    po.save()
    Role.objects.filter(name="Project officer").delete()
    identity.ensure_default_roles()
    assert Role.objects.filter(name="Project officer").count() == 1  # created only if absent
    assert Role.objects.get(name="Placement officer").permissions == ["participants.view"]


def test_no_assignment_means_no_access(people, make_user):
    nobody = make_user("nobody", "Project officer")
    assert ids(nobody) == set()
    assert client(nobody).get("/api/v1/participants").json()["results"] == []


# --- NEW-061: cross-project isolation -------------------------------------------------------


def test_each_officer_sees_their_project_and_the_shared_youth(people, make_user, world):  # noqa: F811
    a = officer(make_user, "ann", world["progs"][0])
    b = officer(make_user, "ben", world["progs"][1])
    p = {k: str(v.pk) for k, v in people.items()}
    assert ids(a) == {p["one"], p["shared"]}
    assert ids(b) == {p["two"], p["shared"]}
    assert names(client(a).get("/api/v1/participants")) == {"Synthetic one", "Synthetic shared"}


def test_an_officer_with_two_projects_sees_both(people, make_user, world):  # noqa: F811
    both = officer(make_user, "cy", *world["progs"])
    assert ids(both) == {str(people[n].pk) for n in ("one", "two", "shared")}


def test_other_projects_and_unassigned_youth_answer_404(people, make_user, world):  # noqa: F811
    a = officer(make_user, "ann", world["progs"][0])
    c = client(a)
    for name in ("two", "orphan"):
        assert c.get(f"/api/v1/participants/{people[name].pk}").status_code == 404
    for name in ("one", "shared"):
        assert c.get(f"/api/v1/participants/{people[name].pk}").status_code == 200
    # writes are refused the same way: existence is not revealed
    r = c.patch(
        f"/api/v1/participants/{people['two'].pk}",
        {"full_name_source": "Changed"},
        content_type="application/json",
    )
    assert r.status_code == 404


def test_an_organisation_wide_role_sees_everyone_including_unassigned(people, make_user):
    steward = make_user("sam", "Data steward")
    assert ids(steward) == {str(p.pk) for p in people.values()}


# --- NEW-059: youth in no project ----------------------------------------------------------


def test_the_data_steward_can_list_youth_in_no_project(people, make_user):
    steward = make_user("sam", "Data steward")
    c = client(steward)
    body = c.get("/api/v1/participants/data-quality").json()
    assert {r["code"]: r["count"] for r in body["rules"]}["no_project"] == 1
    listed = c.get("/api/v1/participants/data-quality/records?rule=no_project").json()
    assert [r["id"] for r in listed["results"]] == [str(people["orphan"].pk)]


def test_a_project_officer_never_reaches_the_orphan_report(people, make_user, world):  # noqa: F811
    a = officer(make_user, "ann", world["progs"][0])
    assert client(a).get("/api/v1/participants/data-quality").status_code == 403


# --- NEW-060: import and export within scope -----------------------------------------------


def test_exports_hold_only_the_officers_projects(people, make_user, world):  # noqa: F811
    a = officer(make_user, "ann", world["progs"][0])
    rows = participants.export_rows(a, {}, ["full_name"])
    assert {str(r["_id"]) for r in rows} == {str(people["one"].pk), str(people["shared"].pk)}
    steward = make_user("sam", "Data steward")
    assert len(participants.export_rows(steward, {}, ["full_name"])) == 4


def test_an_import_row_for_another_project_is_held(world, make_user):  # noqa: F811
    p1 = world["progs"][0]
    a = officer(make_user, "ann", p1)
    steward = make_user("sam", "Data steward")
    tpl = imports.create_template(
        actor=steward,
        source="iso-src",
        columns={
            "Name": "full_name", "Prog": "project_code", "Cohort": "cohort_code",
            "Course": "course_code", "EnrolNo": "enrollment_no",
        },
    )  # fmt: skip
    rows = "\n".join(
        [
            "Name,Prog,Cohort,Course,EnrolNo",
            "Test In,P1,K1,C1,I-1",
            "Test Out,P2,K2,C1,I-2",
        ]
    )
    batch = imports.upload(actor=a, template=tpl, file_name="f.csv", data=rows.encode())
    by_no = {r.row_no: r for r in batch.rows.all()}
    assert not any(e["field"] == "project_code" for e in by_no[1].errors)
    assert by_no[2].outcome == "held"
    assert any("outside the projects" in e["message"] for e in by_no[2].errors)
    # the organisation-wide steward is not limited
    ok = imports.upload(actor=steward, template=tpl, file_name="g.csv", data=rows.encode())
    assert not any("outside the projects" in e["message"] for r in ok.rows.all() for e in r.errors)


def test_a_placement_row_for_another_project_is_held(world, make_user):  # noqa: F811
    a = officer(make_user, "ann", world["progs"][0])
    steward = make_user("sam", "Data steward")
    tpl = imports.create_template(
        actor=steward,
        source="iso-pl",
        target="placements",
        columns={
            "Prog": "project_code", "EnrolNo": "enrollment_no", "Status": "placement_status",
        },
    )  # fmt: skip
    data = b"Prog,EnrolNo,Status\nP2,X-1,Placed\n"
    batch = imports.upload(actor=a, template=tpl, file_name="p.csv", data=data)
    row = batch.rows.get()
    assert any("outside the projects" in e["message"] for e in row.errors)
    assert row.outcome == "held"


def test_commit_holds_a_row_outside_the_committers_projects(world, make_user):  # noqa: F811
    """The upload check is not the only one: the committer's projects are checked again."""
    a = officer(make_user, "ann", world["progs"][0])
    steward = make_user("sam", "Data steward")
    tpl = imports.create_template(
        actor=steward,
        source="iso-commit",
        columns={
            "Name": "full_name", "Prog": "project_code", "Cohort": "cohort_code",
            "Course": "course_code", "EnrolNo": "enrollment_no",
        },
    )  # fmt: skip
    rows = "Name,Prog,Cohort,Course,EnrolNo\nTest In,P1,K1,C1,J-1\nTest Out,P2,K2,C1,J-2\n"
    batch = imports.upload(actor=steward, template=tpl, file_name="c.csv", data=rows.encode())
    assert batch.counts["held"] == 0  # the steward is not limited, so both rows are ready
    imports.approve(actor=steward, batch=batch, create_reference=True)
    done = imports.commit(actor=a, batch=batch)
    by_no = {r.row_no: r for r in done.rows.all()}
    assert by_no[1].committed and not by_no[2].committed
    assert by_no[2].outcome == "held"
    assert any("outside the projects" in e["message"] for e in by_no[2].errors)
    assert done.counts["held"] == 1 and done.counts["create"] == 1


def test_recheck_does_not_release_a_row_outside_the_officers_projects(world, make_user):  # noqa: F811
    a = officer(make_user, "ann", world["progs"][0])
    steward = make_user("sam", "Data steward")
    tpl = imports.create_template(
        actor=steward,
        source="iso-recheck",
        target="placements",
        columns={
            "Prog": "project_code", "EnrolNo": "enrollment_no", "Status": "placement_status",
        },
    )  # fmt: skip
    batch = imports.upload(
        actor=a, template=tpl, file_name="r.csv", data=b"Prog,EnrolNo,Status\nP2,X-1,Placed\n"
    )
    imports.recheck(actor=a, batch=batch)
    row = batch.rows.get()
    assert row.outcome == "held"
    assert any("outside the projects" in e["message"] for e in row.errors)
