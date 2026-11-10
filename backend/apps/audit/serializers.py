from rest_framework import serializers

from .models import AuditEvent


class AuditEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditEvent
        fields = [
            "id",
            "at",
            "actor_id",
            "actor_label",
            "action",
            "object_type",
            "object_id",
            "before",
            "after",
            "reason",
            "request_id",
            "ip",
            "hash",
        ]
        read_only_fields = fields
