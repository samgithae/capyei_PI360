"""Participant core (T-038): the officer-visible tables only.

Not built here: the restricted identity/background tables (D-063, doc 18 pending). Source text
that is not yet settled stays as text: sub-county and ward (D-049), the enrollment number
(D-047, unique per programme but not parsed), the qualification code (D-062)."""

import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.api.access import ScopedQuerySet


class ParticipantQuerySet(ScopedQuerySet):
    def visible_to(self, user, *, archived=False):
        # ``archived``: False hides archived records (soft delete), True shows only them, None both.
        # Programme and cohort scope go through enrollments, a one-to-many join that can repeat a
        # participant, so the result is de-duplicated.
        # Records absorbed by a merge (T-041) are hidden; unmerging brings them back.
        qs = super().visible_to(user).filter(merged_into__isnull=True)
        if archived is not None:
            qs = qs.filter(archived_at__isnull=not archived)
        return qs.distinct()


class Participant(models.Model):
    ACTIVE, COMPLETED, WITHDRAWN, UNKNOWN = "active", "completed", "withdrawn", "unknown"
    STATUSES = [(s, s.capitalize()) for s in (ACTIVE, COMPLETED, WITHDRAWN, UNKNOWN)]
    FEMALE, MALE, OTHER, GENDER_UNKNOWN = "female", "male", "other", "unknown"
    GENDERS = [(g, g.capitalize()) for g in (FEMALE, MALE, OTHER, GENDER_UNKNOWN)]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    full_name_source = models.CharField(max_length=200)  # as written on the source sheet
    given_name = models.CharField(max_length=100, blank=True)
    family_name = models.CharField(max_length=100, blank=True)
    other_names = models.CharField(max_length=100, blank=True)
    gender = models.CharField(max_length=8, choices=GENDERS, default=GENDER_UNKNOWN)
    # Sources give an age, not a birth date (D-062 pending): keep what was stated and when.
    age_at_source = models.PositiveSmallIntegerField(null=True, blank=True)
    age_basis_date = models.DateField(null=True, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    origin_county = models.ForeignKey(
        "configuration.County", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    status = models.CharField(max_length=10, choices=STATUSES, default=UNKNOWN)
    assigned_officer = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    # Set when a steward merges this record into another; kept so the merge can be undone.
    merged_into = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    archived_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ParticipantQuerySet.as_manager()

    scope_map = {
        "programme": "enrollments__programme_id",
        "cohort": "enrollments__cohort_course__cohort_id",
        "region": "origin_county_id",
        "officer": "assigned_officer_id",
    }

    class Meta:
        indexes = [models.Index(fields=["status"]), models.Index(fields=["family_name"])]

    def __str__(self):
        return self.full_name_source


class ParticipantEnrollment(models.Model):
    ENROLLED, COMPLETED, WITHDRAWN, UNKNOWN = "enrolled", "completed", "withdrawn", "unknown"
    STATUSES = [(s, s.capitalize()) for s in (ENROLLED, COMPLETED, WITHDRAWN, UNKNOWN)]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    participant = models.ForeignKey(
        Participant, on_delete=models.CASCADE, related_name="enrollments"
    )
    cohort_course = models.ForeignKey(
        "configuration.CohortCourse", on_delete=models.PROTECT, related_name="+"
    )
    # Denormalised from the cohort so the per-programme uniqueness can be a DB constraint.
    programme = models.ForeignKey(
        "configuration.Programme", on_delete=models.PROTECT, related_name="+"
    )
    institution = models.ForeignKey(
        "configuration.TrainingInstitution", on_delete=models.PROTECT, related_name="+"
    )
    source_enrollment_no = models.CharField(max_length=60, blank=True)
    source_qualification_code = models.CharField(max_length=60, blank=True)
    referral_source_code = models.CharField(max_length=60, blank=True)
    status = models.CharField(max_length=10, choices=STATUSES, default=UNKNOWN)
    enrolled_on = models.DateField(null=True, blank=True)
    completed_on = models.DateField(null=True, blank=True)
    exit_reason = models.CharField(max_length=200, blank=True)
    # Source columns kept as-is under their own labels (import mapping 'extra:<label>').
    # Promoted to real fields later (T-075, T-065, T-087); until then excluded from rules.
    extra = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["programme", "source_enrollment_no"],
                condition=~Q(source_enrollment_no=""),
                name="uniq_enrollment_no_per_programme",
            ),
            models.UniqueConstraint(
                fields=["participant", "cohort_course"], name="uniq_participant_cohort_course"
            ),
        ]

    def __str__(self):
        return f"{self.participant_id}:{self.cohort_course_id}"


class ParticipantContact(models.Model):
    PHONE, EMAIL = "phone", "email"
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    participant = models.ForeignKey(Participant, on_delete=models.CASCADE, related_name="contacts")
    kind = models.CharField(max_length=8, choices=[(PHONE, "Phone"), (EMAIL, "Email")])
    value = models.CharField(max_length=200)
    is_primary = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["participant", "kind"],
                condition=Q(is_primary=True),
                name="one_primary_contact_per_kind",
            )
        ]

    def __str__(self):
        return f"{self.kind}:{self.value}"


class ParticipantResidence(models.Model):
    """Where someone lives, as a history. At most one open row (valid_to empty)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    participant = models.ForeignKey(
        Participant, on_delete=models.CASCADE, related_name="residences"
    )
    county = models.ForeignKey(
        "configuration.County", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    sub_county_source = models.CharField(max_length=100, blank=True)  # D-049: kept as text
    ward_source = models.CharField(max_length=100, blank=True)
    valid_from = models.DateField(null=True, blank=True)
    valid_to = models.DateField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["participant"],
                condition=Q(valid_to__isnull=True),
                name="one_open_residence_per_participant",
            )
        ]

    def __str__(self):
        return str(self.participant_id)


class SourceIdentifier(models.Model):
    """An identifier a participant carries in a source system (never a national ID, which is
    restricted and not built here)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    participant = models.ForeignKey(
        Participant, on_delete=models.CASCADE, related_name="source_identifiers"
    )
    source = models.CharField(max_length=60)
    identifier = models.CharField(max_length=100)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["source", "identifier"], name="uniq_source_identifier")
        ]

    def __str__(self):
        return f"{self.source}:{self.identifier}"


class DuplicateCandidate(models.Model):
    """A pair of records that may be the same person. Held for a steward: nothing here ever merges
    on its own (DATA-05, D-064). ``participant_a`` always sorts before ``participant_b``."""

    OPEN, DISMISSED, MERGED = "open", "dismissed", "merged"
    STATUSES = [(s, s.capitalize()) for s in (OPEN, DISMISSED, MERGED)]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    participant_a = models.ForeignKey(Participant, on_delete=models.CASCADE, related_name="+")
    participant_b = models.ForeignKey(Participant, on_delete=models.CASCADE, related_name="+")
    score = models.FloatField()
    reasons = models.JSONField(default=list)  # rule codes, see duplicates.RULES
    status = models.CharField(max_length=10, choices=STATUSES, default=OPEN)
    note = models.CharField(max_length=500, blank=True)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["participant_a", "participant_b"], name="uniq_duplicate_pair"
            )
        ]
        indexes = [models.Index(fields=["status", "-score"])]

    def __str__(self):
        return f"{self.participant_a_id} ~ {self.participant_b_id}"


class ParticipantMerge(models.Model):
    """One merge, with everything needed to undo it."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    survivor = models.ForeignKey(Participant, on_delete=models.PROTECT, related_name="+")
    absorbed = models.ForeignKey(Participant, on_delete=models.PROTECT, related_name="+")
    candidate = models.ForeignKey(
        DuplicateCandidate, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    snapshot = models.JSONField()
    reason = models.CharField(max_length=500)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    undone_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    undone_at = models.DateTimeField(null=True, blank=True)
    undo_reason = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.absorbed_id} -> {self.survivor_id}"


# --- capability profile: what a youth can do, used by the compatibility rules ----------------
# Everything here is optional. Missing information is never a failure: the rules decide what to
# do with a gap (flag it or leave the check out).

WORK_PATTERNS = [
    ("full_time", "Full time"),
    ("part_time", "Part time"),
    ("shift", "Shift work"),
    ("casual", "Casual or short contract"),
    ("remote", "Remote or home based"),
]


class ProfileFact(models.Model):
    """Who recorded a fact and whether staff have checked it. A youth's own entries are marked
    ``youth`` (self-reported) until a staff member verifies them; any change clears the check."""

    STAFF, YOUTH, IMPORT = "staff", "youth", "import"
    SOURCES = [(STAFF, "Staff"), (YOUTH, "Youth (self-reported)"), (IMPORT, "Import")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source = models.CharField(max_length=6, choices=SOURCES, default=STAFF)
    entered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

    @property
    def verified(self) -> bool:
        return self.verified_at is not None


class ParticipantQualification(ProfileFact):
    participant = models.ForeignKey(
        Participant, on_delete=models.CASCADE, related_name="qualifications"
    )
    level = models.ForeignKey("configuration.QualificationLevel", on_delete=models.PROTECT)
    title = models.CharField(max_length=200, blank=True)  # e.g. "Diploma in Food Production"
    institution = models.CharField(max_length=200, blank=True)
    year_awarded = models.PositiveSmallIntegerField(null=True, blank=True)
    # How well they did, chosen from the grades of this level: "C+", "Second class upper".
    grade = models.ForeignKey(
        "configuration.QualificationGrade", null=True, blank=True, on_delete=models.PROTECT
    )

    class Meta:
        ordering = ["-level__rank", "title"]

    def __str__(self):
        return f"{self.level_id} {self.title}".strip()


class ParticipantSkill(ProfileFact):
    BASIC, WORKING, ADVANCED = 1, 2, 3
    PROFICIENCY = [(BASIC, "Basic"), (WORKING, "Working"), (ADVANCED, "Advanced")]

    participant = models.ForeignKey(Participant, on_delete=models.CASCADE, related_name="skills")
    skill = models.ForeignKey("configuration.Skill", on_delete=models.PROTECT)
    proficiency = models.PositiveSmallIntegerField(choices=PROFICIENCY, default=WORKING)

    class Meta:
        ordering = ["skill__name"]
        constraints = [
            models.UniqueConstraint(fields=["participant", "skill"], name="one_skill_per_youth")
        ]

    def __str__(self):
        return str(self.skill_id)


class ParticipantExperience(ProfileFact):
    participant = models.ForeignKey(
        Participant, on_delete=models.CASCADE, related_name="experience"
    )
    role_title = models.CharField(max_length=200)
    employer_name = models.CharField(max_length=200, blank=True)
    sector = models.ForeignKey(
        "configuration.Sector", null=True, blank=True, on_delete=models.PROTECT
    )
    months = models.PositiveSmallIntegerField()

    class Meta:
        ordering = ["-months", "role_title"]

    def __str__(self):
        return f"{self.role_title} ({self.months} months)"


class ParticipantReadiness(ProfileFact):
    """When and how a youth can start work, and what they would like to do. One row per youth."""

    participant = models.OneToOneField(
        Participant, on_delete=models.CASCADE, related_name="readiness"
    )
    available_from = models.DateField(null=True, blank=True)
    work_patterns = models.JSONField(default=list, blank=True)  # codes from WORK_PATTERNS
    interest_sectors = models.ManyToManyField("configuration.Sector", blank=True, related_name="+")

    def __str__(self):
        return f"readiness:{self.participant_id}"
