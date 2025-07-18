from django.contrib.auth import authenticate, login
from django.contrib.admin import site
from django.shortcuts import render, redirect
from django.views import View
from django import forms
from django.urls import path
from django.utils.translation import gettext_lazy as _
from django.urls import reverse

import logging

logger = logging.getLogger(__name__)
logger.info("=== Admin login debug ===")


class EmailLoginForm(forms.Form):
    email = forms.EmailField(label=_("Email"))
    password = forms.CharField(widget=forms.PasswordInput, label=_("Password"))


class CustomAdminLoginView(View):
    template_name = "admin/custom_login.html"

    def get(self, request):
        logger.info(f"Custom admin login view. Request method: {request.method}")
        logger.info(f"Request path: {request.path}")
        # logger.info(
        #     "Rendering custom_login.html with action:",
        #     str(reverse("custom_admin_login")),
        # )
        form = EmailLoginForm()
        r = render(request, self.template_name, {"form": form})
        return r

    def post(self, request):
        logger.info(f"Custom admin login view. Request method: {request.method}")
        form = EmailLoginForm(request.POST)
        logger.info(f"Form data: {request.POST}")
        if form.is_valid():
            email = form.cleaned_data["email"]
            password = form.cleaned_data["password"]
            user = authenticate(request, username=email, password=password)
            logger.info(f"User authentication: {user}")
            if user is not None and user.is_active and user.is_staff:
                login(request, user)
                logger.info(f"User logged in: {user}")
                user.backend = "api.authentication.EmailBackend"
                response = redirect("/admin/")
                logger.info(f"Redirecting to: {response}")
                logger.info(f"Response location: {response['Location']}")
                return redirect("/admin/")
        return render(
            request,
            self.template_name,
            {"form": form, "error": _("Invalid login credentials.")},
        )


# Подключение URL
# custom_admin_login_url = path(
#     "admin/login/", CustomAdminLoginView.as_view(), name="custom_admin_login"
# )
