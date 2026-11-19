from django.urls import path

from . import views as v

urlpatterns = [
    path("retention", v.RetentionView.as_view()),
    path("retention/run", v.RetentionRunView.as_view()),
    path("retention/<str:code>", v.RetentionClassView.as_view()),
    path("retention/<str:code>/approve", v.RetentionApproveView.as_view()),
    path("retention/<str:code>/revoke", v.RetentionRevokeView.as_view()),
]
