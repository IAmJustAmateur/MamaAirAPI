from django.urls import path
from . import views, views_api
from django.contrib.auth import views as auth_views


urlpatterns = [
    path("users/", views.user_list, name="user_list"),
    path("users/create/", views.create_user, name="create_user"),
    path("users/<int:user_id>/edit/", views.edit_user, name="edit_user"),
    path("users/<int:user_id>/lifestyle/", views.edit_lifestyle, name="edit_lifestyle"),
    path("actions/", views.perform_actions, name="perform_actions"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    #
    path("api/users/", views_api.api_create_user, name="demo_api_create_user"),
    path(
        "api/user-lifestyles/",
        views_api.api_create_or_update_lifestyle,
        name="demo_api_create_lifestyle",
    ),
]
