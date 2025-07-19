"""
URL configuration for agent_api project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.urls import path, include

from django.contrib import admin
from django.urls import path

# from api.admin import admin_site

# from api.admin_login import custom_admin_login_url

from api.admin_login import CustomAdminLoginView

# admin_site.login = CustomAdminLoginView.as_view()

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("api.urls")),
]
