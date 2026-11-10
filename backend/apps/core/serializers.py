from rest_framework import serializers


class HealthSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=["ok", "degraded"])
    database = serializers.ChoiceField(choices=["ok", "unavailable"])
    version = serializers.CharField()


class MeSerializer(serializers.Serializer):
    authenticated = serializers.BooleanField()
    username = serializers.CharField(required=False)
    roles = serializers.ListField(child=serializers.CharField(), required=False)
