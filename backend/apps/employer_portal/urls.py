from django.urls import path

from . import data_views as d
from . import referral_views as rv
from . import views

urlpatterns = [
    path("employer/activate/check", views.ActivateCheckView.as_view()),
    path("employer/activate", views.ActivateView.as_view()),
    path("employer/me", views.EmployerMeView.as_view()),
    path("employer/roles", views.EmployerRolesView.as_view()),
    path("employer/staff", views.EmployerStaffView.as_view()),
    path("employer/staff/<uuid:mpk>", views.EmployerStaffMemberView.as_view()),
    path("employer/dashboard", d.OwnDashboardView.as_view()),
    path("employer/profile", d.OwnProfileView.as_view()),
    path("employer/contacts", d.OwnContactListView.as_view()),
    path("employer/contacts/<uuid:cpk>", d.OwnContactView.as_view()),
    path("employer/opportunities", d.OwnOpportunityListView.as_view()),
    path("employer/opportunities/<uuid:pk>", d.OwnOpportunityView.as_view()),
    path("employer/opportunities/<uuid:pk>/transition", d.OwnOpportunityMoveView.as_view()),
    path("employer/opportunities/<uuid:pk>/requirements", d.OwnRequirementListView.as_view()),
    path(
        "employer/opportunities/<uuid:pk>/requirements/skills",
        d.OwnRequirementSkillsView.as_view(),
    ),
    path(
        "employer/opportunities/<uuid:pk>/requirements/<uuid:rpk>", d.OwnRequirementView.as_view()
    ),
    path("employer/skills", d.OwnSkillSearchView.as_view()),
    path("employer/skills/categories", d.OwnSkillCategoryView.as_view()),
    path("employer/skills/popular", d.OwnSkillPopularView.as_view()),
    path("employer/referrals", rv.OwnReferralListView.as_view()),
    path("employer/referral-reasons", rv.OwnReferralReasonsView.as_view()),
    path("employer/referrals/<uuid:pk>", rv.OwnReferralView.as_view()),
    path("employer/referrals/<uuid:pk>/transition", rv.OwnReferralMoveView.as_view()),
    path("employer/referrals/<uuid:pk>/interview", rv.OwnReferralInterviewView.as_view()),
    path("employer/referrals/<uuid:pk>/cv", rv.OwnReferralCvView.as_view()),
    path("employer/referrals/<uuid:pk>/cv.pdf", rv.OwnReferralCvPdfView.as_view()),
    path("employer/referrals/<uuid:pk>/photo", rv.OwnReferralPhotoView.as_view()),
    path("employers/<uuid:pk>/users", views.StaffEmployerUsersView.as_view()),
    path("employers/<uuid:pk>/users/<uuid:mpk>", views.StaffEmployerUserView.as_view()),
]
