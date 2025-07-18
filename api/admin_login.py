from django.contrib.auth import authenticate, login
from django.contrib.admin import site
from django.shortcuts import render, redirect
from django.views import View
from django import forms
from django.urls import path
from django.utils.translation import gettext_lazy as _

import logging

logger = logging.getLogger(__name__)


class EmailLoginForm(forms.Form):
    email = forms.EmailField(label=_("Email"))
    password = forms.CharField(widget=forms.PasswordInput, label=_("Password"))


class CustomAdminLoginView(View):
    template_name = "admin/custom_login.html"

    def get(self, request):
        form = EmailLoginForm()
        r = render(request, self.template_name, {"form": form})
        return r

    def post(self, request):
        form = EmailLoginForm(request.POST)
        logger.info(f"Custom admin login view. Request method: {request.method}")
        logger.info(f"Form data: {request.POST}")
        if form.is_valid():
            email = form.cleaned_data["email"]
            password = form.cleaned_data["password"]
            user = authenticate(request, username=email, password=password)
            logger.info(f"User authentication: {user}")
            if user is not None and user.is_active and user.is_staff:
                login(request, user)
                logger.info(f"User logged in: {user}")
                return redirect("/admin/")
        return render(
            request,
            self.template_name,
            {"form": form, "error": _("Invalid login credentials.")},
        )


# Подключение URL
custom_admin_login_url = path(
    "admin/login/", CustomAdminLoginView.as_view(), name="custom_admin_login"
)
