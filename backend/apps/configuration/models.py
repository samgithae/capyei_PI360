"""Reference data, feature flags and protected settings (CMP-14; doc 14 §5.1).

Every reference record has a UUID id and a stable code. Records point to ids, never names, so a
rename is a new label in ``ReferenceLabel`` and links never break. Records are deactivated,
never deleted."""

import uuid

from django.conf import settings
from django.db import models


def norm(text: str) -> str:
    """Case, spacing and punctuation-insensitive form used for uniqueness and alias matching."""
    return " ".join("".join(c if c.isalnum() else " " for c in text.casefold()).split())


class Reference(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=40)
    name = models.CharField(max_length=200)
    name_normalised = models.CharField(max_length=200, editable=False)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        ordering = ["name"]

    def __str__(self):
        return f"{self.code} {self.name}"

    def save(self, *args, **kwargs):
        self.name_normalised = norm(self.name)
        super().save(*args, **kwargs)


class Sector(Reference):
    class Meta(Reference.Meta):
        constraints = [
            models.UniqueConstraint(fields=["code"], name="uniq_sector_code"),
            models.UniqueConstraint(fields=["name_normalised"], name="uniq_sector_name"),
        ]


class County(Reference):
    """Kenya county; code is the official 01-47 number."""

    class Meta(Reference.Meta):
        verbose_name_plural = "counties"
        constraints = [models.UniqueConstraint(fields=["code"], name="uniq_county_code")]


class SubCounty(Reference):
    county = models.ForeignKey(County, on_delete=models.PROTECT, related_name="sub_counties")

    class Meta(Reference.Meta):
        verbose_name_plural = "sub-counties"
        constraints = [
            models.UniqueConstraint(fields=["county", "code"], name="uniq_subcounty_code"),
            models.UniqueConstraint(
                fields=["county", "name_normalised"], name="uniq_subcounty_name"
            ),
        ]


class Ward(Reference):
    sub_county = models.ForeignKey(SubCounty, on_delete=models.PROTECT, related_name="wards")

    class Meta(Reference.Meta):
        constraints = [
            models.UniqueConstraint(fields=["sub_county", "code"], name="uniq_ward_code"),
            # The same ward name may exist under two sub-counties (doc 17 P-03).
            models.UniqueConstraint(
                fields=["sub_county", "name_normalised"], name="uniq_ward_name"
            ),
        ]


class TrainingInstitution(Reference):
    kind = models.CharField(
        max_length=10, choices=[("vtc", "VTC"), ("other", "Other")], default="vtc"
    )
    county = models.ForeignKey(County, on_delete=models.PROTECT, related_name="institutions")
    ward = models.ForeignKey(
        Ward, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )

    class Meta(Reference.Meta):
        constraints = [models.UniqueConstraint(fields=["code"], name="uniq_institution_code")]


class Programme(Reference):
    funder = models.CharField(max_length=200, blank=True)
    start = models.DateField(null=True, blank=True)
    end = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=12, default="active")

    class Meta(Reference.Meta):
        constraints = [models.UniqueConstraint(fields=["code"], name="uniq_programme_code")]


class Course(Reference):
    programme = models.ForeignKey(Programme, on_delete=models.PROTECT, related_name="courses")
    default_sector = models.ForeignKey(
        Sector, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    level = models.CharField(max_length=20, blank=True)

    class Meta(Reference.Meta):
        constraints = [
            models.UniqueConstraint(fields=["programme", "code"], name="uniq_course_code")
        ]


class Cohort(Reference):
    """Structure lives in fields, not inside the name (doc 14 §1). ``name`` holds the label."""

    programme = models.ForeignKey(Programme, on_delete=models.PROTECT, related_name="cohorts")
    institution = models.ForeignKey(
        TrainingInstitution, on_delete=models.PROTECT, related_name="cohorts"
    )
    intake_year = models.PositiveSmallIntegerField()
    batch_no = models.PositiveSmallIntegerField()
    phase = models.PositiveSmallIntegerField(default=1)
    year_of_study = models.PositiveSmallIntegerField(default=1)
    start = models.DateField(null=True, blank=True)
    end = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=12, default="active")

    class Meta(Reference.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "programme",
                    "institution",
                    "intake_year",
                    "batch_no",
                    "phase",
                    "year_of_study",
                ],
                name="uniq_cohort_identity",
            ),
            models.UniqueConstraint(fields=["programme", "code"], name="uniq_cohort_code"),
        ]


class CohortCourse(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    cohort = models.ForeignKey(Cohort, on_delete=models.PROTECT, related_name="offerings")
    course = models.ForeignKey(Course, on_delete=models.PROTECT, related_name="offerings")
    capacity = models.PositiveIntegerField(null=True, blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["cohort", "course"], name="uniq_cohort_course")
        ]

    def __str__(self):
        return f"{self.cohort_id}:{self.course_id}"


class ReferenceAlias(models.Model):
    """A source spelling that resolves to one record, so "KWALE" and "Kwale " are one county."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    kind = models.CharField(max_length=20)
    object_id = models.UUIDField()
    scope = models.CharField(max_length=64, blank=True)  # parent id, e.g. the sub-county of a ward
    alias = models.CharField(max_length=200)
    alias_normalised = models.CharField(max_length=200, editable=False)
    source = models.CharField(max_length=60, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["kind", "scope", "alias_normalised"], name="uniq_alias")
        ]

    def __str__(self):
        return self.alias

    def save(self, *args, **kwargs):
        self.alias_normalised = norm(self.alias)
        super().save(*args, **kwargs)


class ReferenceLabel(models.Model):
    """History of names: a rename adds a row; the record and its links stay the same."""

    kind = models.CharField(max_length=20)
    object_id = models.UUIDField()
    name = models.CharField(max_length=200)
    valid_from = models.DateTimeField(auto_now_add=True)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        indexes = [models.Index(fields=["kind", "object_id"])]
        ordering = ["valid_from", "pk"]

    def __str__(self):
        return self.name


class ReferralReason(Reference):
    """Controlled reason for an unsuccessful referral outcome (FR-18). The list is a proposed
    default until CAP-YEI confirms it (D-037); administrators manage it as reference data."""

    REJECTED, WITHDRAWN, NO_RESPONSE, ANY = "rejected", "withdrawn", "no_response", "any"
    APPLIES = [
        (REJECTED, "Rejected"),
        (WITHDRAWN, "Withdrawn"),
        (NO_RESPONSE, "No response"),
        (ANY, "Any unsuccessful outcome"),
    ]

    applies_to = models.CharField(max_length=12, choices=APPLIES, default=ANY)
    needs_note = models.BooleanField(default=False)  # e.g. "Other": the note says what happened

    class Meta(Reference.Meta):
        constraints = [
            models.UniqueConstraint(fields=["code"], name="uniq_referral_reason_code"),
            models.UniqueConstraint(fields=["name_normalised"], name="uniq_referral_reason_name"),
        ]


class QualificationLevel(Reference):
    """A level on the qualification ladder. ``rank`` orders the levels so a rule can ask for "at
    least a diploma". The list is a proposed default until CAP-YEI confirms it; administrators
    manage it as reference data."""

    rank = models.PositiveSmallIntegerField()

    class Meta(Reference.Meta):
        ordering = ["rank"]
        constraints = [
            models.UniqueConstraint(fields=["code"], name="uniq_qualification_level_code"),
            models.UniqueConstraint(
                fields=["name_normalised"], name="uniq_qualification_level_name"
            ),
            models.UniqueConstraint(fields=["rank"], name="uniq_qualification_level_rank"),
        ]


def grade_key(text: str) -> str:
    """Like ``norm`` but keeps + and -, so "C+", "C" and "C-" stay different grades."""
    return " ".join(text.casefold().split())


class QualificationGrade(Reference):
    """A result a youth can get at a qualification level, e.g. A to E for secondary school.
    ``rank`` orders the grades within the level, higher is better, so an opportunity can ask for
    "C or above". Administrators manage the list as reference data."""

    level = models.ForeignKey(QualificationLevel, on_delete=models.PROTECT, related_name="grades")
    rank = models.PositiveSmallIntegerField()

    class Meta(Reference.Meta):
        ordering = ["level__rank", "-rank"]
        constraints = [
            models.UniqueConstraint(fields=["code"], name="uniq_qualification_grade_code"),
            models.UniqueConstraint(
                fields=["level", "name_normalised"], name="uniq_qualification_grade_name"
            ),
            models.UniqueConstraint(fields=["level", "rank"], name="uniq_qualification_grade_rank"),
        ]

    def save(self, *args, **kwargs):
        self.name_normalised = grade_key(self.name)
        models.Model.save(self, *args, **kwargs)  # skip Reference.save, which strips + and -


class Skill(Reference):
    """A skill or competency a youth may have and an opportunity may ask for."""

    category = models.CharField(max_length=80, blank=True)

    class Meta(Reference.Meta):
        constraints = [
            models.UniqueConstraint(fields=["code"], name="uniq_skill_code"),
            models.UniqueConstraint(fields=["name_normalised"], name="uniq_skill_name"),
        ]


class FeatureFlag(models.Model):
    """A switch with an optional audience. ``environments`` and ``roles`` empty = everyone."""

    key = models.SlugField(max_length=60, unique=True)
    description = models.CharField(max_length=300, blank=True)
    enabled = models.BooleanField(default=False)
    environments = models.JSONField(default=list, blank=True)
    roles = models.JSONField(default=list, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.key


class ProtectedSetting(models.Model):
    """A value an administrator may change only after step-up re-authentication."""

    key = models.CharField(max_length=80, unique=True)
    value = models.JSONField()
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )

    def __str__(self):
        return self.key
