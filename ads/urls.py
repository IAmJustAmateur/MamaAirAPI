from django.urls import path

from .views import AdClickView, AdImpressionView, AdView

urlpatterns = [
    path("", AdView.as_view(), name="ads"),
    path("impression/", AdImpressionView.as_view(), name="ads-impression"),
    path("click/", AdClickView.as_view(), name="ads-click"),
]
