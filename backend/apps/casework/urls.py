from django.urls import path

from . import views

urlpatterns = [
    path("cases/queue", views.QueueView.as_view()),
    path("placements", views.PlacementListView.as_view()),
    path("placements/summary", views.PlacementSummaryView.as_view()),
    path("placements/options", views.PlacementOptionsView.as_view()),
    path("placements/<uuid:pk>", views.PlacementDetailView.as_view()),
    path("placements/<uuid:pk>/end", views.PlacementEndView.as_view()),
    path("placements/<uuid:pk>/verify", views.PlacementVerifyView.as_view()),
    path("placements/<uuid:pk>/history", views.PlacementHistoryView.as_view()),
]
