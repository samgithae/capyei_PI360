from django.urls import path

from . import views

urlpatterns = [
    path("cases/queue", views.QueueView.as_view()),
    path("participants/duplicates/<uuid:pk>/resolve", views.MergeResolveView.as_view()),
    path("placements", views.PlacementListView.as_view()),
    path("placements/summary", views.PlacementSummaryView.as_view()),
    path("placements/options", views.PlacementOptionsView.as_view()),
    path("placements/<uuid:pk>", views.PlacementDetailView.as_view()),
    path("placements/<uuid:pk>/end", views.PlacementEndView.as_view()),
    path("placements/<uuid:pk>/exit-feedback", views.PlacementExitFeedbackView.as_view()),
    path("placements/<uuid:pk>/change-employer", views.PlacementChangeEmployerView.as_view()),
    path("placements/<uuid:pk>/verify", views.PlacementVerifyView.as_view()),
    path("placements/<uuid:pk>/history", views.PlacementHistoryView.as_view()),
    path("followups", views.FollowUpListView.as_view()),
    path("followups/summary", views.FollowUpSummaryView.as_view()),
    path("followups/options", views.FollowUpOptionsView.as_view()),
    path("followups/steps", views.FollowUpStepListView.as_view()),
    path("followups/steps/<uuid:pk>", views.FollowUpStepDetailView.as_view()),
    path("followups/<uuid:pk>", views.FollowUpDetailView.as_view()),
    path("followups/<uuid:pk>/history", views.FollowUpHistoryView.as_view()),
    path("followups/<uuid:pk>/attempts", views.FollowUpAttemptView.as_view()),
    path("followups/<uuid:pk>/complete", views.FollowUpCompleteView.as_view()),
    path("followups/<uuid:pk>/unreachable", views.FollowUpUnreachableView.as_view()),
    path("followups/<uuid:pk>/cancel", views.FollowUpCancelView.as_view()),
    path("followups/<uuid:pk>/assign", views.FollowUpAssignView.as_view()),
]
