from rest_framework import serializers


class MeSerializer(serializers.Serializer):
    authenticated = serializers.BooleanField()
    username = serializers.CharField(required=False)
    roles = serializers.ListField(child=serializers.CharField(), required=False)
