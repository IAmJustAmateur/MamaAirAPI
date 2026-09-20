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

from django.conf import settings
from django.conf.urls.static import static
from django.urls import path, include

from django.contrib import admin
from api.auth_pages import account_link
from django.urls import path
from debug_toolbar.toolbar import debug_toolbar_urls

urlpatterns = [
    path("reset-password", account_link, {"purpose": "reset"}, name="reset-password-page"),
    path("verify-email", account_link, {"purpose": "verify"}, name="verify-email-page"),
    path("admin/", admin.site.urls),
    path("api/", include("api.urls")),
    path("demo/", include("demo_interface.urls")),
]

from debug_toolbar.toolbar import debug_toolbar_urls

urlpatterns += debug_toolbar_urls()

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
