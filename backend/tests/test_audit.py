"""Audit framework (T-037, SEC-09): append-only, hash-chained, viewable by role."""

import pytest
from django.contrib.auth.models import Permission, User
from django.db import connection, transaction
from django.db.utils import InternalError, ProgrammingError

from apps.api import context
from apps.audit import services as audit
from apps.audit.chain import GENESIS
from apps.audit.models import AuditEvent, ImmutableError

postgres_only = pytest.mark.skipif(
    connection.vendor != "postgresql", reason="database triggers are PostgreSQL only"
)


@pytest.fixture
def audit_db(transactional_db):
    """Real commits, for tests that need them. Django empties tables between such tests with
    TRUNCATE, which the append-only trigger rightly blocks. So: triggers on while the test
    runs; afterwards empty the table and switch off only the truncate trigger so Django's
    flush can run. The next use of this fixture switches it back on."""
    pg = connection.vendor == "postgresql"
    with connection.cursor() as c:
        if pg:
            c.execute("ALTER TABLE audit_auditevent ENABLE TRIGGER USER")
    yield
    with connection.cursor() as c:
        if pg:
            c.execute("ALTER TABLE audit_auditevent DISABLE TRIGGER USER")
        c.execute("DELETE FROM audit_auditevent")
        if pg:
            c.execute("ALTER TABLE audit_auditevent ENABLE TRIGGER audit_no_update_delete")
            c.execute("ALTER TABLE audit_auditevent DISABLE TRIGGER audit_no_truncate")


def make(n=1, **kw):
    return [
        audit.record(
            actor=kw.get("actor"),
            action="referral.stage_changed",
            object_type="referral",
            object_id=100 + i,
            before={"stage": "offered"},
            after={"stage": "placed"},
            reason="test",
        )
        for i in range(n)
    ]


@pytest.mark.django_db
def test_record_stores_actor_diff_and_context():
    user = User.objects.create_user("officer", password="a-long-test-password")
    context.request_id.set("req-12345678")
    context.client_ip.set("10.1.2.3")
    try:
        ev = audit.record(
            actor=user,
            action="profile.edited",
            object_type="participant",
            object_id=7,
            before={"phone": "a"},
            after={"phone": "b"},
            reason="correction",
        )
    finally:
        context.request_id.set(None)
        context.client_ip.set(None)
    ev.refresh_from_db()
    assert (ev.actor_id, ev.actor_label) == (user.pk, "officer")
    assert (ev.object_type, ev.object_id) == ("participant", "7")
    assert ev.before == {"phone": "a"} and ev.after == {"phone": "b"}
    assert ev.request_id == "req-12345678" and ev.ip == "10.1.2.3"


@pytest.mark.django_db
def test_system_actor_and_chain_links():
    first, second = make(2)
    assert first.actor_label == "system" and first.actor_id is None
    assert first.prev_hash == GENESIS
    assert second.prev_hash == first.hash
    assert audit.verify_chain().ok


@pytest.mark.django_db
def test_empty_chain_is_valid():
    assert audit.verify_chain() == audit.ChainResult(True, 0)


@pytest.mark.django_db
def test_model_refuses_update_and_delete():
    (ev,) = make()
    ev.reason = "changed"
    with pytest.raises(ImmutableError):
        ev.save()
    with pytest.raises(ImmutableError):
        ev.delete()
    with pytest.raises(ImmutableError):
        AuditEvent.objects.all().update(reason="x")
    with pytest.raises(ImmutableError):
        AuditEvent.objects.all().delete()


def test_tampering_is_detected_at_the_first_bad_row(audit_db):
    events = make(4)
    # Bypass every guard (raw SQL, trigger removed) the way an attacker with DB owner rights could.
    with connection.cursor() as c:
        if connection.vendor == "postgresql":
            c.execute("ALTER TABLE audit_auditevent DISABLE TRIGGER USER")
        c.execute("UPDATE audit_auditevent SET reason = 'edited' WHERE id = %s", [events[1].pk])
        if connection.vendor == "postgresql":
            c.execute("ALTER TABLE audit_auditevent ENABLE TRIGGER USER")
    result = audit.verify_chain()
    assert (result.ok, result.first_bad_id) == (False, events[1].pk)
    assert result.checked == 1


def test_deleting_a_row_is_detected(audit_db):
    events = make(3)
    with connection.cursor() as c:
        if connection.vendor == "postgresql":
            c.execute("ALTER TABLE audit_auditevent DISABLE TRIGGER USER")
        c.execute("DELETE FROM audit_auditevent WHERE id = %s", [events[1].pk])
        if connection.vendor == "postgresql":
            c.execute("ALTER TABLE audit_auditevent ENABLE TRIGGER USER")
    result = audit.verify_chain()
    assert (result.ok, result.first_bad_id) == (False, events[2].pk)
    assert "link" in result.problem


@postgres_only
@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE audit_auditevent SET reason = 'x'",
        "DELETE FROM audit_auditevent",
        "TRUNCATE audit_auditevent",
    ],
)
def test_database_itself_rejects_update_delete_truncate(audit_db, sql):
    make(2)
    with pytest.raises((ProgrammingError, InternalError)) as err:
        with transaction.atomic(), connection.cursor() as c:
            c.execute(sql)
    assert "append-only" in str(err.value)
    assert AuditEvent.objects.count() == 2


@postgres_only
def test_concurrent_writers_keep_one_unbroken_chain(audit_db):
    import threading

    from django.db import connections

    errors = []

    def worker():
        try:
            make(5)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)
        finally:
            connections.close_all()

    threads = [threading.Thread(target=worker) for _ in range(4)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert errors == []
    assert audit.verify_chain() == audit.ChainResult(True, 20)


@pytest.mark.django_db
def test_viewer_requires_permission(client):
    make(2)
    assert client.get("/api/v1/audit/events").status_code in (401, 403)
    plain = User.objects.create_user("plain", password="a-long-test-password")
    client.force_login(plain)
    assert client.get("/api/v1/audit/events").status_code == 403
    plain.user_permissions.add(Permission.objects.get(codename="view_auditevent"))
    client.force_login(User.objects.get(pk=plain.pk))
    res = client.get("/api/v1/audit/events")
    assert res.status_code == 200
    body = res.json()
    assert [e["object_id"] for e in body["results"]] == ["101", "100"]  # newest first
    assert "hash" in body["results"][0]


@pytest.mark.django_db
def test_viewer_filters_and_is_read_only(client):
    make(3)
    audit.record(actor=None, action="rule.activated", object_type="rule", object_id=1)
    admin = User.objects.create_superuser("root", password="a-long-test-password")
    client.force_login(admin)
    by_action = client.get("/api/v1/audit/events?action=rule.activated").json()["results"]
    assert [e["object_type"] for e in by_action] == ["rule"]
    by_obj = client.get("/api/v1/audit/events?object_type=referral&object_id=101").json()
    assert len(by_obj["results"]) == 1
    bad = client.get("/api/v1/audit/events?from=not-a-date")
    assert bad.status_code == 400 and bad.json()["errors"][0]["field"] == "from"
    for method in ("post", "put", "patch", "delete"):
        res = getattr(client, method)("/api/v1/audit/events")
        assert res.status_code in (403, 405), method


@pytest.mark.django_db
def test_verify_command(capsys):
    from django.core.management import call_command

    make(2)
    call_command("verify_audit_chain")
    assert "intact: 2 events" in capsys.readouterr().out
