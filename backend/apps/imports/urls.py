from django.urls import path

from . import views as v

urlpatterns = [
    path("imports/templates", v.TemplateListView.as_view()),
    path("imports/extra", v.ExtraSummaryView.as_view()),
    path("imports/extra/promote", v.ExtraPromoteView.as_view()),
    path("imports/inspect", v.InspectView.as_view()),
    path("imports/batches", v.BatchListView.as_view()),
    path("imports/batches/<uuid:pk>", v.BatchDetailView.as_view()),
    path("imports/batches/<uuid:pk>/rows", v.BatchRowsView.as_view()),
    path("imports/batches/<uuid:pk>/errors", v.BatchErrorsView.as_view()),
    path("imports/batches/<uuid:pk>/reconciliation", v.BatchReconciliationView.as_view()),
    path("imports/templates/<uuid:pk>/contract", v.TemplateContractView.as_view()),
    path("imports/batches/<uuid:pk>/approve", v.BatchApproveView.as_view()),
    path("imports/batches/<uuid:pk>/commit", v.BatchCommitView.as_view()),
    path("imports/batches/<uuid:pk>/rollback", v.BatchRollbackView.as_view()),
    path("imports/batches/<uuid:pk>/signoff", v.BatchSignoffView.as_view()),
    path("imports/batches/<uuid:pk>/cancel", v.BatchCancelView.as_view()),
    path("imports/batches/<uuid:pk>/review", v.PlacementReviewView.as_view()),
    path("imports/batches/<uuid:pk>/review/employers", v.PlacementEmployerDecisionView.as_view()),
    path("imports/batches/<uuid:pk>/review/statuses", v.PlacementStatusMapView.as_view()),
    path(
        "imports/batches/<uuid:pk>/review/statuses/proposed",
        v.PlacementProposedStatusesView.as_view(),
    ),
    path("imports/batches/<uuid:pk>/recheck", v.BatchRecheckView.as_view()),
]
