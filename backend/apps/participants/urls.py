from django.urls import path

from . import views as v

urlpatterns = [
    path("participants/filters", v.FilterOptionsView.as_view()),
    path("participants", v.ParticipantListView.as_view()),
    path("participants/<uuid:pk>", v.ParticipantDetailView.as_view()),
]
