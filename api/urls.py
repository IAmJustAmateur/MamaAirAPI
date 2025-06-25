# api/urls.py

from django.urls import path
from rest_framework.authtoken.views import obtain_auth_token
from .views import (
    UserProfileView,
    UserLifestyleView,
    UserMommySymptomsView,
    UserBabySymptomsView,
    HealthInsightView,
    MovementCSVUploadView,
    EnvironmentView,
)
from rest_framework.schemas import get_schema_view
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

urlpatterns = [
    path("auth/login/", obtain_auth_token, name="login"),
    path("profile/", UserProfileView.as_view(), name="profile"),
    path("lifestyle/", UserLifestyleView.as_view(), name="lifestyle"),
    path("symptoms/mommy/", UserMommySymptomsView.as_view(), name="symptoms-mommy"),
    path("symptoms/baby/", UserBabySymptomsView.as_view(), name="symptoms-baby"),
    path("movements/upload", MovementCSVUploadView.as_view(), name="movements-upload"),
    path("advice/", HealthInsightView.as_view(), name="advice"),
    path("air-exposure/", EnvironmentView.as_view(), name="air-exposure"),
    # Swagger/OpenAPI
    path("schema/", SpectacularAPIView.as_view(), name="schema"),
    path("docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
]
