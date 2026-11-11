"""Employer registry (T-044, FR-11): employers and their contacts.

Sector and county are references to configuration ids, so renames never break links. Sub-county
stays text (D-049). Employers are deactivated, never deleted (the one exception: reversing a
steward's cluster decision removes the employers that decision created, if still unused)."""

import uuid

from django.conf import settings
from django.db import models

from apps.configuration.services import normalise


class Employer(models.Model):
    ACTIVE, INACTIVE, PROSPECT = "active", "inactive", "prospect"
    STATUSES = [(s, s.capitalize()) for s in (ACTIVE, INACTIVE, PROSPECT)]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    name_normalised = models.CharField(max_length=200, editable=False, db_index=True)
    sector = models.ForeignKey(
        "configuration.Sector", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    county = models.ForeignKey(
        "configuration.County", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    sub_county = models.CharField(max_length=100, blank=True)
    address = models.CharField(max_length=200, blank=True)
    website = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=10, choices=STATUSES, default=ACTIVE)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        self.name_normalised = normalise(self.name)
        super().save(*args, **kwargs)


class EmployerContact(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employer = models.ForeignKey(Employer, on_delete=models.CASCADE, related_name="contacts")
    name = models.CharField(max_length=150)
    role = models.CharField(max_length=100, blank=True)
    email = models.CharField(max_length=200, blank=True)
    phone = models.CharField(max_length=50, blank=True)
    is_primary = models.BooleanField(default=False)

    class Meta:
        ordering = ["-is_primary", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["employer"],
                condition=models.Q(is_primary=True),
                name="one_primary_contact_per_employer",
            )
        ]

    def __str__(self):
        return self.name


class Opportunity(models.Model):
    """A job, internship or apprenticeship an employer offers (FR-12, FR-13).

    Lifecycle (D-008/D-010 pending, so draft is an assumption): draft -> open -> closed or
    expired; closed and expired can be reopened with a future closing date. Closed and expired
    opportunities accept no new referrals."""

    DRAFT, OPEN, CLOSED, EXPIRED = "draft", "open", "closed", "expired"
    STATUSES = [(s, s.capitalize()) for s in (DRAFT, OPEN, CLOSED, EXPIRED)]
    TRANSITIONS = {
        DRAFT: {OPEN},
        OPEN: {CLOSED, EXPIRED},
        CLOSED: {OPEN},
        EXPIRED: {OPEN},
    }
    TYPES = [(t, t.capitalize()) for t in ("job", "internship", "apprenticeship", "other")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employer = models.ForeignKey(Employer, on_delete=models.PROTECT, related_name="opportunities")
    title = models.CharField(max_length=200)
    kind = models.CharField(max_length=14, choices=TYPES, default="job")
    sector = models.ForeignKey(
        "configuration.Sector", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    county = models.ForeignKey(
        "configuration.County", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    location = models.CharField(max_length=200, blank=True)
    positions = models.PositiveIntegerField(default=1)
    description = models.TextField(blank=True)
    start_date = models.DateField(null=True, blank=True)
    closing_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUSES, default=DRAFT, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title


class OpportunityRequirement(models.Model):
    """One condition of an opportunity: mandatory eligibility or preferred factor (FR-14)."""

    FACTORS = [
        (f, f.capitalize()) for f in ("skill", "qualification", "location", "availability", "other")
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    opportunity = models.ForeignKey(
        Opportunity, on_delete=models.CASCADE, related_name="requirements"
    )
    factor = models.CharField(max_length=14, choices=FACTORS)
    description = models.CharField(max_length=300)
    is_mandatory = models.BooleanField(default=False)

    class Meta:
        ordering = ["-is_mandatory", "factor", "description"]

    def __str__(self):
        return f"{self.factor}: {self.description}"


class ClusterDecision(models.Model):
    """A steward's decision about one group of source spellings (T-087 stage B, doc 15 §8).

    Grouping only suggests; nothing is merged until a steward decides (R-23). A decision can be
    reversed: its aliases are removed and any employers it created are deleted, provided nothing
    else has started to use them."""

    LINK, CREATE, APART = "link", "create", "apart"
    ACTIONS = [(LINK, "Link to an existing employer"), (CREATE, "Create one new employer"),
               (APART, "Keep apart: one new employer per spelling")]  # fmt: skip

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    key = models.CharField(max_length=200, db_index=True)
    action = models.CharField(max_length=6, choices=ACTIONS)
    spellings = models.JSONField(default=list)
    created_employers = models.JSONField(default=list)  # employer ids this decision made
    source = models.CharField(max_length=100, blank=True)  # e.g. the import batch id
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, related_name="+"
    )
    decided_at = models.DateTimeField(auto_now_add=True)
    reversed_at = models.DateTimeField(null=True, blank=True)
    reversed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        ordering = ["-decided_at"]

    def __str__(self):
        return f"{self.action}: {self.key}"


class EmployerAlias(models.Model):
    """One source spelling of an employer's name. Every spelling is kept (doc 14 §5.3)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employer = models.ForeignKey(Employer, on_delete=models.CASCADE, related_name="aliases")
    source_name = models.CharField(max_length=200, unique=True)
    name_key = models.CharField(max_length=200, db_index=True)
    decision = models.ForeignKey(
        ClusterDecision, null=True, blank=True, on_delete=models.SET_NULL, related_name="aliases"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.source_name
