"""PI360-NEW-002: the synthetic CAP-YEI demo seed builds what the new features need, stays
synthetic, refuses to run outside development, and is safe to run twice."""

import importlib.util
import re
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model

from apps.employers.models import EmployerFeedback
from apps.participants.models import (
    Participant,
    ParticipantContact,
    ParticipantEnrollment,
    ParticipantSkill,
)
from apps.placements.models import Placement

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "seed_capyei_demo.py"


def _load():
    spec = importlib.util.spec_from_file_location("seed_capyei_demo", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # the module name stops it seeding on import
    return module


@pytest.fixture
def seeded(db, settings):
    settings.DEBUG = True
    return _load().seed()


@pytest.mark.django_db
def test_refuses_outside_development(settings):
    settings.DEBUG = False
    with pytest.raises(RuntimeError):
        _load().seed()
    assert not Participant.objects.exists()


def test_two_projects_and_one_youth_in_both(seeded):
    assert seeded["youth"] == 13
    shared = Participant.objects.get(pk=seeded["shared_participant"])
    projects = set(shared.enrollments.values_list("project__code", flat=True))
    assert projects == {"SYN-A", "SYN-B"}


def test_project_officer_sees_own_project_and_the_shared_youth(seeded):
    User = get_user_model()
    a = User.objects.get(username="demo.officer.a")
    b = User.objects.get(username="demo.officer.b")
    seen_a = set(Participant.objects.visible_to(a).values_list("pk", flat=True))
    seen_b = set(Participant.objects.visible_to(b).values_list("pk", flat=True))
    shared = Participant.objects.get(pk=seeded["shared_participant"]).pk
    assert len(seen_a) == 7 and len(seen_b) == 7  # six own + the shared youth
    assert seen_a & seen_b == {shared}
    assert not a.has_usable_password() and not b.has_usable_password()


def test_placement_chain_feedback_and_unverified_skills(seeded):
    episodes = Placement.objects.filter(
        enrollment__participant_id=seeded["shared_participant"]
    ).order_by("start_date")
    assert [e.end_date is None for e in episodes] == [False, True]
    assert episodes[0].employer_id != episodes[1].employer_id
    assert Placement.objects.filter(pathway=Placement.SELF).count() == 1
    assert EmployerFeedback.objects.filter(rating__lte=2).count() == 2
    skills = ParticipantSkill.objects.all()
    assert skills.count() == 12
    assert all(s.source == ParticipantSkill.YOUTH and s.verified_at is None for s in skills)


def test_safe_to_run_twice(seeded, settings):
    before = (
        Participant.objects.count(),
        ParticipantEnrollment.objects.count(),
        Placement.objects.count(),
        EmployerFeedback.objects.count(),
    )
    _load().seed()
    after = (
        Participant.objects.count(),
        ParticipantEnrollment.objects.count(),
        Placement.objects.count(),
        EmployerFeedback.objects.count(),
    )
    assert before == after


def test_every_identifier_is_obviously_synthetic(seeded):
    for name in Participant.objects.values_list("full_name_source", flat=True):
        assert name.startswith("Synthetic Youth ")
    for kind, value in ParticipantContact.objects.values_list("kind", "value"):
        if kind == "phone":
            assert re.fullmatch(r"07000001\d\d", value)
        else:
            assert value.endswith("@synthetic.example")
