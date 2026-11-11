from django.urls import path

from . import views as v

urlpatterns = [
    path("employers/filters", v.FilterOptionsView.as_view()),
    path("employers", v.EmployerListView.as_view()),
    path("employers/check-name", v.EmployerCheckView.as_view()),
    path("employers/archive", v.EmployerArchiveView.as_view()),
    path("employers/restore", v.EmployerRestoreView.as_view()),
    path("employers/<uuid:pk>", v.EmployerDetailView.as_view()),
    path("employers/<uuid:pk>/history", v.EmployerHistoryView.as_view()),
    path("employers/<uuid:pk>/contacts", v.ContactListView.as_view()),
    path("employers/<uuid:pk>/contacts/<uuid:cpk>", v.ContactDetailView.as_view()),
    path("opportunities", v.OpportunityListView.as_view()),
    path("opportunities/archive", v.OpportunityArchiveView.as_view()),
    path("opportunities/restore", v.OpportunityRestoreView.as_view()),
    path("opportunities/<uuid:pk>", v.OpportunityDetailView.as_view()),
    path("opportunities/<uuid:pk>/transition", v.OpportunityTransitionView.as_view()),
    path("opportunities/<uuid:pk>/history", v.OpportunityHistoryView.as_view()),
    path("opportunities/<uuid:pk>/requirements", v.RequirementListView.as_view()),
    path("opportunities/<uuid:pk>/requirements/<uuid:rpk>", v.RequirementDetailView.as_view()),
]
