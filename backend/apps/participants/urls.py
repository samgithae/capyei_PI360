from django.urls import path

from . import cv_views as cv
from . import duplicate_views as d
from . import profile_views as pv
from . import quality_views as dq
from . import skill_views as sk
from . import views as v

urlpatterns = [
    path("participants/filters", v.FilterOptionsView.as_view()),
    path("participants", v.ParticipantListView.as_view()),
    path("participants/check-name", v.NameCheckView.as_view()),
    path("participants/duplicates", d.DuplicateListView.as_view()),
    path("participants/duplicates/scan", d.DuplicateScanView.as_view()),
    path("participants/duplicates/<uuid:pk>/dismiss", d.DuplicateDismissView.as_view()),
    path("participants/duplicates/<uuid:pk>/review", d.DuplicateReviewView.as_view()),
    path("participants/duplicates/<uuid:pk>/merge", d.DuplicateMergeView.as_view()),
    path("participants/duplicates/<uuid:pk>/complete", d.DuplicateCompleteView.as_view()),
    path("participants/merges", d.MergeListView.as_view()),
    path("participants/merges/<uuid:pk>/undo", d.MergeUndoView.as_view()),
    path("participants/data-quality", dq.QualitySummaryView.as_view()),
    path("participants/data-quality/records", dq.QualityRecordsView.as_view()),
    path("participants/corrections", dq.CorrectionListView.as_view()),
    path("participants/corrections/<uuid:pk>/resolve", dq.CorrectionResolveView.as_view()),
    path("participants/review/mark", v.ParticipantReviewBulkView.as_view()),
    path("participants/<uuid:pk>/review", v.ParticipantReviewView.as_view()),
    path("participants/<uuid:pk>/contacts", v.ContactsView.as_view()),
    path("participants/<uuid:pk>/disability", v.DisabilityView.as_view()),
    path("participants/<uuid:pk>/consent", v.ConsentView.as_view()),
    path("participants/skills", sk.StaffSearch.as_view()),
    path("participants/skills/categories", sk.StaffCategories.as_view()),
    path("participants/skills/popular", sk.StaffPopular.as_view()),
    path("participants/skills/add", sk.StaffAdd.as_view()),
    path("participants/profile-options", pv.ProfileOptionsView.as_view()),
    path("participants/profile-import", pv.ProfileImportView.as_view()),
    path("participants/profile-import-template", pv.ProfileImportTemplateView.as_view()),
    path("participants/<uuid:pk>/profile", pv.ProfileView.as_view()),
    path("participants/<uuid:pk>/profile/verify", pv.ProfileVerifyView.as_view()),
    path("participants/<uuid:pk>/verification", pv.ProfileVerificationView.as_view()),
    path("participants/<uuid:pk>/activity", pv.ActivityView.as_view()),
    path("participants/<uuid:pk>/cv", cv.CvView.as_view()),
    path("participants/<uuid:pk>/cv.pdf", cv.CvPdfView.as_view()),
    path("participants/<uuid:pk>/photo", cv.PhotoView.as_view()),
    path("participants/<uuid:pk>/enrollments", v.EnrollmentCreateView.as_view()),
    path("participants/<uuid:pk>/residence", v.ResidenceView.as_view()),
    path("participants/archive", v.ParticipantArchiveView.as_view()),
    path("participants/restore", v.ParticipantRestoreView.as_view()),
    path("participants/<uuid:pk>", v.ParticipantDetailView.as_view()),
    path(
        "participants/<uuid:pk>/enrollments/<uuid:enrollment_id>",
        v.EnrollmentDetailView.as_view(),
    ),
]
