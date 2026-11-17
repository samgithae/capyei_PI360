from django.urls import path

from . import case_views as c
from . import views as v

urlpatterns = [
    path("interventions", c.InterventionListView.as_view()),
    path("interventions/options", c.InterventionOptionsView.as_view()),
    path("interventions/<uuid:pk>", c.InterventionDetailView.as_view()),
    path("interventions/<uuid:pk>/move", c.InterventionMoveView.as_view()),
    path("interventions/<uuid:pk>/assign", c.InterventionAssignView.as_view()),
    path("interventions/<uuid:pk>/history", c.InterventionHistoryView.as_view()),
    path("referrals", v.ReferralListView.as_view()),
    path("referrals/bulk", v.ReferralBulkView.as_view()),
    path("referrals/summary", v.ReferralSummaryView.as_view()),
    path("referrals/by-opportunity", v.ReferralByOpportunityView.as_view()),
    path("referrals/reasons", v.ReferralReasonsView.as_view()),
    path("referrals/assignees", v.ReferralAssigneesView.as_view()),
    path("referrals/<uuid:pk>", v.ReferralDetailView.as_view()),
    path("referrals/<uuid:pk>/transition", v.ReferralTransitionView.as_view()),
    path("referrals/<uuid:pk>/interview", v.ReferralInterviewView.as_view()),
    path("referrals/<uuid:pk>/correct", v.ReferralCorrectView.as_view()),
    path("referrals/<uuid:pk>/assign", v.ReferralAssignView.as_view()),
    path("referrals/<uuid:pk>/history", v.ReferralAuditView.as_view()),
]
