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
    # Privacy notice and consent (T-054). The statuses and wording are provisional until CAP-YEI's
    # data protection lead decides D-015; the MIS carries none of this, so imports start unrecorded.
    CONSENT_NOT_RECORDED, CONSENT_GIVEN = "not_recorded", "given"
    CONSENTS = [
        (CONSENT_NOT_RECORDED, "Not recorded"),
        (CONSENT_GIVEN, "Given"),
        ("declined", "Declined"),
        ("withdrawn", "Withdrawn"),
    ]
    consent_status = models.CharField(max_length=12, choices=CONSENTS, default=CONSENT_NOT_RECORDED)
    consent_notice_version = models.CharField(max_length=40, blank=True)
    consent_recorded_on = models.DateField(null=True, blank=True)
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
    # CV details. ``year_awarded`` is the completion year; it stays empty while studying.
    field_of_study = models.CharField(max_length=200, blank=True)
    start_year = models.PositiveSmallIntegerField(null=True, blank=True)
    currently_studying = models.BooleanField(default=False)

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


EMPLOYMENT_TYPES = [
    ("full_time", "Full time"),
    ("part_time", "Part time"),
    ("contract", "Contract"),
    ("casual", "Casual or temporary"),
    ("self_employed", "Self-employed"),
]


class ParticipantExperience(ProfileFact):
    participant = models.ForeignKey(
        Participant, on_delete=models.CASCADE, related_name="experience"
    )
    role_title = models.CharField(max_length=200)
    employer_name = models.CharField(max_length=200, blank=True)
    sector = models.ForeignKey(
        "configuration.Sector", null=True, blank=True, on_delete=models.PROTECT
    )
    # Total months worked. The rules read it. When dates are given it is worked out from them,
    # so it is never asked for twice.
    months = models.PositiveSmallIntegerField()
    employment_type = models.CharField(max_length=14, choices=EMPLOYMENT_TYPES, blank=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    is_current = models.BooleanField(default=False)
    responsibilities = models.TextField(blank=True)
    achievements = models.TextField(blank=True)

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
    # CV: the short introduction, what they are looking for, and whether they have worked before.
    summary = models.TextField(blank=True)
    preferred_roles = models.JSONField(default=list, blank=True)  # short free-text job titles
    preferred_counties = models.ManyToManyField(
        "configuration.County", blank=True, related_name="+"
    )
    willing_to_relocate = models.BooleanField(null=True, blank=True)  # empty = not said
    no_work_experience = models.BooleanField(default=False)  # said they have never worked

    def __str__(self):
        return f"readiness:{self.participant_id}"


class ParticipantCertification(ProfileFact):
    """A certificate, short course or vocational training."""

    participant = models.ForeignKey(
        Participant, on_delete=models.CASCADE, related_name="certifications"
    )
    name = models.CharField(max_length=200)
    issuer = models.CharField(max_length=200, blank=True)
    year_obtained = models.PositiveSmallIntegerField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["-year_obtained", "name"]

    def __str__(self):
        return self.name


PRACTICAL_KINDS = [
    ("internship", "Internship"),
    ("attachment", "Attachment"),
    ("apprenticeship", "Apprenticeship"),
    ("volunteering", "Volunteering"),
]


class ParticipantPractical(ProfileFact):
    """Internship, attachment, apprenticeship or volunteering: practical experience that is not
    a job, which matters for youth with little formal employment."""

    participant = models.ForeignKey(
        Participant, on_delete=models.CASCADE, related_name="practical_experience"
    )
    organisation = models.CharField(max_length=200)
    role = models.CharField(max_length=200, blank=True)
    kind = models.CharField(max_length=14, choices=PRACTICAL_KINDS)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["-start_date", "organisation"]

    def __str__(self):
        return f"{self.kind} at {self.organisation}"


LANGUAGE_LEVELS = [
    ("basic", "Basic"),
    ("conversational", "Conversational"),
    ("fluent", "Fluent"),
    ("native", "Native or bilingual"),
]


class ParticipantLanguage(ProfileFact):
    participant = models.ForeignKey(Participant, on_delete=models.CASCADE, related_name="languages")
    language = models.CharField(max_length=60)
    proficiency = models.CharField(max_length=14, choices=LANGUAGE_LEVELS, default="fluent")

    class Meta:
        ordering = ["language"]

    def __str__(self):
        return self.language


class ParticipantPhoto(models.Model):
    """The optional CV photo: one small square JPEG per youth, kept in the database so it is
    served only to people allowed to see the profile (never as a public file)."""

    participant = models.OneToOneField(Participant, on_delete=models.CASCADE, related_name="photo")
    content = models.BinaryField()
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"photo:{self.participant_id}"


class ProfileVerification(models.Model):
    """The record of how staff checked one profile entry (a qualification, a skill and so on).

    ``ProfileFact.verified_at`` stays the single yes/no that the rules read; this adds what a
    plain yes/no cannot say: still pending, rejected, or needs checking again after the youth
    changed the entry, plus how it was checked and a note. One row per entry. Free-text notes
    are for staff only and are never written to the audit log."""

    PENDING, VERIFIED, REJECTED, REASSESS = "pending", "verified", "rejected", "needs_reassessment"
    STATUSES = [
        (PENDING, "Pending"),
        (VERIFIED, "Verified"),
        (REJECTED, "Rejected"),
        (REASSESS, "Needs reassessment"),
    ]
    METHODS = [
        ("document", "Document seen"),
        ("reference", "Reference or referee"),
        ("institution", "Confirmed with institution or employer"),
        ("interview", "Interview or conversation"),
        ("assessment", "Assessment or practical test"),
        ("other", "Other"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    participant = models.ForeignKey(
        Participant, on_delete=models.CASCADE, related_name="verifications"
    )
    kind = models.CharField(max_length=14)
    fact_id = models.UUIDField()
    status = models.CharField(max_length=20, choices=STATUSES, default=PENDING)
    method = models.CharField(max_length=14, choices=METHODS, blank=True)
    notes = models.CharField(max_length=1000, blank=True)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["kind", "fact_id"], name="one_verification_per_entry")
        ]
        indexes = [models.Index(fields=["participant"])]

    def __str__(self):
        return f"{self.kind}:{self.fact_id} {self.status}"


class ParticipantCorrection(models.Model):
    """A fix an officer made in PI360 to a value that came from the MIS (T-074, D-025).

    The MIS stays the system of record, so a fix is kept here with who made it and when, listed
    in a correction export, and protected: an import must not overwrite it until the MIS carries
    the same value (``confirmed``) or a reviewer decides. States: ``open`` (MIS not yet updated),
    ``confirmed`` (MIS now agrees, or a reviewer marked it updated), ``closed`` (a reviewer took
    the MIS value instead). A ``conflict_*`` value is what a later import tried to write over it."""

    OPEN, CONFIRMED, CLOSED = "open", "confirmed", "closed"
    STATES = [(OPEN, "Waiting for the MIS"), (CONFIRMED, "MIS updated"), (CLOSED, "MIS value kept")]
    FIELDS = [
        ("full_name", "Name"),
        ("gender", "Gender"),
        ("age", "Age"),
        ("county", "County"),
        ("status", "Enrolment status"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    participant = models.ForeignKey(
        Participant, on_delete=models.CASCADE, related_name="corrections"
    )
    # Only for a field that lives on the enrolment (status): which enrolment it is.
    enrollment = models.ForeignKey(
        ParticipantEnrollment, null=True, blank=True, on_delete=models.CASCADE, related_name="+"
    )
    field = models.CharField(max_length=12, choices=FIELDS)
    before_raw = models.CharField(max_length=200, blank=True)
    before_label = models.CharField(max_length=200, blank=True)  # what the MIS had
    after_raw = models.CharField(max_length=200, blank=True)  # compared with the import
    after_label = models.CharField(max_length=200, blank=True)  # what the officer set
    state = models.CharField(max_length=10, choices=STATES, default=OPEN, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    conflict_raw = models.CharField(max_length=200, blank=True)
    conflict_label = models.CharField(max_length=200, blank=True)
    conflict_batch = models.CharField(max_length=64, blank=True)
    conflict_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_how = models.CharField(max_length=20, blank=True)
    closed_note = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ["-updated_at"]
        indexes = [models.Index(fields=["participant", "state"])]

    def __str__(self):
        return f"{self.participant_id}:{self.field}:{self.state}"
