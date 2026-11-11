from django.urls import path

from . import duplicate_views as d
from . import views as v

urlpatterns = [
    path("participants/filters", v.FilterOptionsView.as_view()),
    path("participants", v.ParticipantListView.as_view()),
    path("participants/duplicates", d.DuplicateListView.as_view()),
    path("participants/duplicates/scan", d.DuplicateScanView.as_view()),
    path("participants/duplicates/<uuid:pk>/dismiss", d.DuplicateDismissView.as_view()),
    path("participants/duplicates/<uuid:pk>/merge", d.DuplicateMergeView.as_view()),
    path("participants/merges", d.MergeListView.as_view()),
    path("participants/merges/<uuid:pk>/undo", d.MergeUndoView.as_view()),
    path("participants/archive", v.ParticipantArchiveView.as_view()),
    path("participants/restore", v.ParticipantRestoreView.as_view()),
    path("participants/<uuid:pk>", v.ParticipantDetailView.as_view()),
    path(
        "participants/<uuid:pk>/enrollments/<uuid:enrollment_id>",
        v.EnrollmentDetailView.as_view(),
    ),
]
