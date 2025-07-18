from django.contrib.auth import authenticate, login
from django.contrib.admin import site
from django.shortcuts import render, redirect
from django.views import View
from django import forms
from django.urls import path
from django.utils.translation import gettext_lazy as _
from django.urls import reverse
from django.http import HttpResponse

import logging

from .models import User

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
            logger.info(f"Email: {email}")
            logger.info(f"Password: {password}")
            user = authenticate(request, username=email, password=password)
            logger.info(f"User authentication: {user}")
            if user is not None and user.is_active and user.is_staff:
                # response = redirect("/admin/")
                response = HttpResponse("Logged in!")
                user.backend = "api.authentication.EmailBackend"
                login(request, user)
                for h, v in response.items():
                    if h.lower() == "set-cookie":
                        logger.info(f"Set-Cookie header: {v}")
                logger.info(f"User logged in: {user}")
                response = redirect("/admin/")
                logger.info(f"Redirecting to: {response}")
                logger.info(f"Response location: {response['Location']}")
                return response
        else:
            logger.info(f"Invalid form data: {form.errors}")
            email = request.POST.get("email")
            password = request.POST.get("password")
            logger.info(f"Email: {email}")
            logger.info(f"Password: {password}")
            user = User.objects.filter(email=email).first()
            if user:
                logger.info(f"User found: {user}")
                logger.info(f"email: {user.email}")
            else:
                logger.info("User not found")

        return render(
            request,
            self.template_name,
            {"form": form, "error": _("Invalid login credentials.")},
        )


# Подключение URL
# custom_admin_login_url = path(
#     "admin/login/", CustomAdminLoginView.as_view(), name="custom_admin_login"
# )
