"""Rule sets and their versions (T-047, doc 07 §2). A rule set is one configurable piece of a
module ("compatibility-default" in Module B). Each change to it is a new version.

A version's definition can be edited only while it is a draft. Once it leaves draft the model
refuses the change (``Immutable``), so a result can always be reproduced from its version."""

import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q


class Immutable(Exception):
    pass


class RuleSet(models.Model):
    MODULES = [
        ("A", "Module A: placement support priority"),
        ("B", "Module B: opportunity compatibility"),
        ("C", "Module C: employer reliability"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    module = models.CharField(max_length=1, choices=MODULES)
    code = models.SlugField(max_length=60, unique=True)
    name = models.CharField(max_length=120)
    purpose = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+",
    )  # fmt: skip
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["module", "name"]

    def __str__(self):
        return self.code


class RuleVersionQuerySet(models.QuerySet):
    """Bulk update and delete would skip the model's own guard, so refuse them here too."""

    def update(self, **kwargs):
        frozen = RuleVersion.FROZEN & set(kwargs)
        if frozen and self.exclude(status=RuleVersion.DRAFT).exists():
            raise Immutable("Only a draft rule version can be changed.")
        if kwargs.get("status") in RuleVersion.BEFORE_ACTIVE and (
            self.filter(status__in=RuleVersion.WENT_LIVE).exists()
        ):
            raise Immutable("A version that has been active cannot go back to draft.")
        return super().update(**kwargs)

    def delete(self):
        if self.exclude(status=RuleVersion.DRAFT).exists():
            raise Immutable("Only a draft rule version can be discarded.")
        return super().delete()


class RuleVersion(models.Model):
    DRAFT, IN_REVIEW, APPROVED, ACTIVE, RETIRED = (
        "draft", "in_review", "approved", "active", "retired"
    )  # fmt: skip
    STATUSES = [
        (DRAFT, "Draft"),
        (IN_REVIEW, "In review"),
        (APPROVED, "Approved"),
        (ACTIVE, "Active"),
        (RETIRED, "Retired"),
    ]
    BEFORE_ACTIVE = frozenset({DRAFT, IN_REVIEW, APPROVED})
    WENT_LIVE = frozenset({ACTIVE, RETIRED})
    # Fields that describe what the rule *is*. They freeze when the version leaves draft.
    FROZEN = frozenset({"definition", "rule_set", "rule_set_id", "number"})

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    rule_set = models.ForeignKey(RuleSet, on_delete=models.PROTECT, related_name="versions")
    number = models.PositiveIntegerField()
    status = models.CharField(max_length=10, choices=STATUSES, default=DRAFT, db_index=True)
    definition = models.JSONField(default=dict)  # factors and parameters (pi360_rules)
    change_notes = models.TextField(blank=True)
    cloned_from = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    # The version this one replaced when it was activated; the fallback on deactivation.
    replaced = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+",
    )  # fmt: skip
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+",
    )  # fmt: skip
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+",
    )  # fmt: skip
    activated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+",
    )  # fmt: skip
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    effective_from = models.DateTimeField(null=True, blank=True)  # set on activation
    retired_at = models.DateTimeField(null=True, blank=True)
    used_at = models.DateTimeField(null=True, blank=True)  # first time a result used it

    objects = RuleVersionQuerySet.as_manager()

    class Meta:
        ordering = ["rule_set", "-number"]
        constraints = [
            models.UniqueConstraint(fields=["rule_set", "number"], name="uniq_rule_version_no"),
            # The database itself refuses a second active version of the same rule set.
            models.UniqueConstraint(
                fields=["rule_set"], condition=Q(status="active"), name="uniq_active_rule_version"
            ),
        ]

    def __str__(self):
        return f"{self.rule_set_id} v{self.number} ({self.status})"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            stored = (
                type(self)._base_manager.filter(pk=self.pk)
                .values("status", "definition", "rule_set_id", "number")
                .first()
            )  # fmt: skip
            if stored and stored["status"] != self.DRAFT:
                now = (self.definition, self.rule_set_id, self.number)
                if now != (stored["definition"], stored["rule_set_id"], stored["number"]):
                    raise Immutable("Only a draft rule version can be changed.")
            if stored and stored["status"] in self.WENT_LIVE and self.status in self.BEFORE_ACTIVE:
                raise Immutable("A version that has been active cannot go back to draft.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.status != self.DRAFT:
            raise Immutable("Only a draft rule version can be discarded.")
        return super().delete(*args, **kwargs)
