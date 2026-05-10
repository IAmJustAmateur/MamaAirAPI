# api/urls.py

from django.urls import path
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)
from .views import (
    UserProfileView,
    UserLifestyleView,
    MommySymptomsChecklistView,
    UserMommySymptomsSelectionView,
    BabySymptomsChecklistView,
    UserBabySymptomsSelectionView,
    HealthInsightView,
    MovementCSVUploadView,
    MovementJSONUploadView,
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
    MetaChoicesView,
    #
    ExposureHistoryView,
    #
    RecommendationCompletionView,
    WellbeingCatalogView,
    UserWellbeingLogView,
    DailyCheckinView,
    DailyTaskListView,
    TaskCompletionView,
)
from .auth_views import GoogleAuthView
from .auth.views_firebase import FirebaseAuthView
from api.views_debug import DebugExposureUpsertView, DebugExposureRecomputeView
from rest_framework.schemas import get_schema_view
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from django.conf import settings

from .jwt_refresh import LoggingTokenRefreshView

# app_name = "api"

urlpatterns = [
    path("auth/register/", RegisterView.as_view(), name="register"),
    path("auth/token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    # path("auth/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path(
        "auth/token/refresh/",
        LoggingTokenRefreshView.as_view(),
        name="token_refresh",
    ),
    path("auth/logout/", LogoutView.as_view(), name="logout"),
    path("auth/password-change/", PasswordChangeView.as_view(), name="password-change"),
    path("auth/delete-account/", DeleteAccountView.as_view(), name="delete-account"),
    path("profile/", UserProfileView.as_view(), name="profile"),
    path("set-language/", SetLanguageView.as_view(), name="set-language"),
    path("lifestyle/", UserLifestyleView.as_view(), name="lifestyle"),
    path(
        "symptoms/mommy/checklist/",
        MommySymptomsChecklistView.as_view(),
        name="symptoms-mommy-checklist",
    ),
    # Mommy
    path(
        "symptoms/mommy/selection/",
        UserMommySymptomsSelectionView.as_view(),
        name="symptoms-mommy-selection",
    ),
    # Baby
    path(
        "symptoms/baby/checklist/",
        BabySymptomsChecklistView.as_view(),
        name="symptoms-baby-checklist",
    ),
    path(
        "symptoms/baby/selection/",
        UserBabySymptomsSelectionView.as_view(),
        name="symptoms-baby-selection",
    ),
    path("movements/upload/", MovementCSVUploadView.as_view(), name="movements-upload"),
    path(
        "movements/upload/json/",
        MovementJSONUploadView.as_view(),
        name="movements-upload-json",
    ),
    #
    path("advice/", HealthInsightView.as_view(), name="advice"),
    path("info/current/", CurrentAdviceView.as_view(), name="current-advices"),
    path("air-exposure/", EnvironmentView.as_view(), name="air-exposure"),
    #
    path("exposure/history/", ExposureHistoryView.as_view(), name="exposure-history"),
    #
    path("meta/choices/", MetaChoicesView.as_view(), name="meta-choices"),
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
    path(
        "recommendation-completion/",
        RecommendationCompletionView.as_view(),
        name="recommendation-completion",
    ),
    path("wellbeing/", WellbeingCatalogView.as_view(), name="wellbeing-catalog"),
    path("wellbeing/log/", UserWellbeingLogView.as_view(), name="wellbeing-log"),
    path("daily-checkin/", DailyCheckinView.as_view(), name="daily-checkin"),
    path("daily-tasks/", DailyTaskListView.as_view(), name="daily-tasks"),
    path("task-completion/", TaskCompletionView.as_view(), name="task-completion"),
]
urlpatterns += [
    path("auth/google/", GoogleAuthView.as_view(), name="auth-google"),
]
urlpatterns += [
    path("login/", login_view, name="login"),
]
urlpatterns += [
    path("auth/firebase/", FirebaseAuthView.as_view(), name="auth-firebase"),
]

debug_urls = [
    path(
        "debug/air-exposure/upsert/",
        DebugExposureUpsertView.as_view(),
        name="debug-exposure-upsert",
    ),
    path(
        "debug/air-exposure/recompute/",
        DebugExposureRecomputeView.as_view(),
        name="debug-exposure-recompute",
    ),
]

if settings.DEBUG or settings.DJANGO_ENV in {"development", "staging"}:
    urlpatterns += debug_urls
