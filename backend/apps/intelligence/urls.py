from django.urls import path

from . import views as v

urlpatterns = [
    path("opportunities/<uuid:pk>/suggestions", v.OpportunitySuggestionsView.as_view()),
    path("rules", v.RuleSetListView.as_view()),
    path("rules/operators", v.OperatorListView.as_view()),
    path("rules/<uuid:pk>", v.RuleSetDetailView.as_view()),
    path("rules/versions/<uuid:pk>", v.RuleVersionView.as_view()),
    path("rules/versions/<uuid:pk>/clone", v.RuleVersionCloneView.as_view()),
    path("rules/versions/<uuid:pk>/submit", v.RuleVersionSubmitView.as_view()),
    path("rules/versions/<uuid:pk>/return", v.RuleVersionReturnView.as_view()),
    path("rules/versions/<uuid:pk>/approve", v.RuleVersionApproveView.as_view()),
    path("rules/versions/<uuid:pk>/activate", v.RuleVersionActivateView.as_view()),
    path("rules/versions/<uuid:pk>/deactivate", v.RuleVersionDeactivateView.as_view()),
    path("rules/versions/<uuid:pk>/history", v.RuleVersionHistoryView.as_view()),
]
