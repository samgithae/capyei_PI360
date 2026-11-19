from django.urls import path

from . import views as v

urlpatterns = [
    path("reporting/dashboard", v.DashboardView.as_view()),
    path("reporting/drilldown", v.DrilldownView.as_view()),
    path("reporting/reports", v.ReportIndexView.as_view()),
    path("reporting/reports/filters", v.ReportFiltersView.as_view()),
    path("reporting/reports/<slug:slug>", v.ReportView.as_view()),
    path("reporting/reports/<slug:slug>/export", v.ReportExportView.as_view()),
    path("exports", v.ExportsView.as_view()),
    path("exports/table/<slug:table>", v.TableExportView.as_view()),
    path("exports/fields/<slug:table>", v.TableFieldsView.as_view()),
    path("exports/<uuid:pk>/download", v.ExportDownloadView.as_view()),
]
