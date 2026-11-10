from django.urls import path

from . import views as v

urlpatterns = [
    path("employers/filters", v.FilterOptionsView.as_view()),
    path("employers", v.EmployerListView.as_view()),
    path("employers/check-name", v.EmployerCheckView.as_view()),
    path("employers/<uuid:pk>", v.EmployerDetailView.as_view()),
    path("employers/<uuid:pk>/history", v.EmployerHistoryView.as_view()),
    path("employers/<uuid:pk>/contacts", v.ContactListView.as_view()),
    path("employers/<uuid:pk>/contacts/<uuid:cpk>", v.ContactDetailView.as_view()),
]
