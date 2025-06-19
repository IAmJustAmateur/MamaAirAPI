from django.urls import path
from .views import RegisterView, LoginView, MovementUploadView, AnalyzeView
from .views import (
    UserDetailView,
    PatientMedicationViewSet,
    PatientMedicationDetailView,
    PatientSupplementsViewSet,
    PatientSupplementsDetailView,
    PatientLyfeStyleTrackerViewSet,
    PatientLyfeStyleTrackerDetailView,
)

urlpatterns = [
    path("register/", RegisterView.as_view(), name="register"),
    path("login/", LoginView.as_view(), name="login"),
    path("upload_movements/", MovementUploadView.as_view(), name="upload_movements"),
    path("analyze/", AnalyzeView.as_view(), name="analyze"),
]

urlpatterns += [
    path("user/<int:pk>/", UserDetailView.as_view(), name="user-detail"),
    path(
        "medications/",
        PatientMedicationViewSet.as_view(),
        name="patient-medication-list",
    ),
    path(
        "medications/<int:pk>/",
        PatientMedicationDetailView.as_view(),
        name="patient-medication-detail",
    ),
    path(
        "supplements/",
        PatientSupplementsViewSet.as_view(),
        name="patient-supplements-list",
    ),
    path(
        "supplements/<int:pk>/",
        PatientSupplementsDetailView.as_view(),
        name="patient-supplements-detail",
    ),
    path("lifestyle/", PatientLyfeStyleTrackerViewSet.as_view(), name="lifestyle-list"),
    path(
        "lifestyle/<int:pk>/",
        PatientLyfeStyleTrackerDetailView.as_view(),
        name="lifestyle-detail",
    ),
]
