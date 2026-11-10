from django.urls import path

from .views import HealthView, MeView

urlpatterns = [
    path("health", HealthView.as_view(), name="health"),
    path("me", MeView.as_view(), name="me"),
]
