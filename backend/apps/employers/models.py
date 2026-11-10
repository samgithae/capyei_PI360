"""Employer registry (T-044, FR-11): employers and their contacts.

Sector and county are references to configuration ids, so renames never break links. Sub-county
stays text (D-049). Employers are deactivated, never deleted."""

import uuid

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
