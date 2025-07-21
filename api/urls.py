# api/urls.py

from django.urls import path
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)
from .views import (
    UserProfileView,
    UserLifestyleView,
    UserMommySymptomsView,
    UserBabySymptomsView,
    HealthInsightView,
    MovementCSVUploadView,
    EnvironmentView,
    CurrentAdviceView,
    LogoutView,
    PasswordChangeView,
    WeeklyExposureView,
    SummaryView,
    SetLanguageView,
    DeleteAccountView,
    RegisterView,
    # remove later
    login_view,
)
from rest_framework.schemas import get_schema_view
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

# app_name = "api"

urlpatterns = [
    path("auth/register/", RegisterView.as_view(), name="register"),
    path("auth/token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("auth/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("auth/logout/", LogoutView.as_view(), name="logout"),
    path("auth/password-change/", PasswordChangeView.as_view(), name="password-change"),
    path("auth/delete-account/", DeleteAccountView.as_view(), name="delete-account"),
    path("profile/", UserProfileView.as_view(), name="profile"),
    path("set-language/", SetLanguageView.as_view(), name="set-language"),
    path("lifestyle/", UserLifestyleView.as_view(), name="lifestyle"),
    path("symptoms/mommy/", UserMommySymptomsView.as_view(), name="symptoms-mommy"),
    path("symptoms/baby/", UserBabySymptomsView.as_view(), name="symptoms-baby"),
    path("movements/upload", MovementCSVUploadView.as_view(), name="movements-upload"),
    #
    path("advice/", HealthInsightView.as_view(), name="advice"),
    path("info/current/", CurrentAdviceView.as_view(), name="current-advices"),
    path("air-exposure/", EnvironmentView.as_view(), name="air-exposure"),
    #
    path(
        "exposure-per-weeks/",
        WeeklyExposureView.as_view(),
        name="exposure-per-weeks",
    ),
    path("summary/", SummaryView.as_view(), name="summary"),
    # Swagger/OpenAPI
    path("schema/", SpectacularAPIView.as_view(), name="schema"),
    path("docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
]
urlpatterns += [
    path("login/", login_view, name="login"),
]
