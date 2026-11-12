from django.urls import path

from . import views

urlpatterns = [
    path("participants/<uuid:pk>/invite", views.InviteView.as_view()),
    path("youth/activate/check", views.ActivateCheckView.as_view()),
    path("youth/activate", views.ActivateView.as_view()),
    path("youth/me", views.YouthMeView.as_view()),
    path("youth/consent", views.YouthConsentView.as_view()),
    path("youth/profile", views.YouthProfileView.as_view()),
    path("youth/details", views.YouthDetailsView.as_view()),
    path("youth/notices", views.YouthNoticesView.as_view()),
    path("youth/placement", views.YouthPlacementView.as_view()),
    path("youth/journey", views.YouthJourneyView.as_view()),
    path("youth/opportunities/<uuid:pk>", views.YouthOpportunityView.as_view()),
]
