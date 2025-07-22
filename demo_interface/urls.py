from django.urls import path
from . import views
from django.contrib.auth import views as auth_views


urlpatterns = [
    path("users/", views.user_list, name="user_list"),
    path("users/create/", views.create_user, name="create_user"),
    path("users/<int:user_id>/edit/", views.edit_user, name="edit_user"),
    path("actions/", views.perform_actions, name="perform_actions"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
]
