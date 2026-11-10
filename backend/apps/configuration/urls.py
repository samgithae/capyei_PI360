from django.urls import path

from . import views as v

urlpatterns = [
    path("config/reference/<str:kind>", v.ReferenceListView.as_view()),
    path("config/reference/<str:kind>/<uuid:pk>", v.ReferenceDetailView.as_view()),
    path("config/reference/<str:kind>/<uuid:pk>/deactivate", v.ReferenceDeactivateView.as_view()),
    path("config/reference/<str:kind>/<uuid:pk>/reactivate", v.ReferenceReactivateView.as_view()),
    path("config/reference/<str:kind>/<uuid:pk>/aliases", v.ReferenceAliasView.as_view()),
    path("config/flags", v.FlagListView.as_view()),
    path("config/flags/<str:key>", v.FlagDetailView.as_view()),
    path("config/settings", v.SettingListView.as_view()),
]
