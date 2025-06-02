from django.urls import path
from .views import RegisterView, LoginView, MovementUploadView, AnalyzeView

urlpatterns = [
    path("register/", RegisterView.as_view(), name="register"),
    path("login/", LoginView.as_view(), name="login"),
    path("upload_movements/", MovementUploadView.as_view(), name="upload_movements"),
    path("analyze/", AnalyzeView.as_view(), name="analyze"),
]
