from django.urls import path

from . import views as v

urlpatterns = [
    path("referrals", v.ReferralListView.as_view()),
    path("referrals/summary", v.ReferralSummaryView.as_view()),
    path("referrals/reasons", v.ReferralReasonsView.as_view()),
    path("referrals/assignees", v.ReferralAssigneesView.as_view()),
    path("referrals/<uuid:pk>", v.ReferralDetailView.as_view()),
    path("referrals/<uuid:pk>/transition", v.ReferralTransitionView.as_view()),
    path("referrals/<uuid:pk>/correct", v.ReferralCorrectView.as_view()),
    path("referrals/<uuid:pk>/assign", v.ReferralAssignView.as_view()),
    path("referrals/<uuid:pk>/history", v.ReferralAuditView.as_view()),
]
