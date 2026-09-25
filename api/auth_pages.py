import secrets

from django.shortcuts import render, redirect
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_http_methods
from rest_framework.exceptions import ValidationError

from .email_auth import ConfirmInput, confirm_account


@sensitive_post_parameters("new_password", "password_confirm")
@never_cache
@csrf_protect
@require_http_methods(["GET", "POST"])
def account_link(request, purpose):
    script_nonce = secrets.token_urlsafe(16)
    session_key = "account_link_" + purpose
    if request.method == "GET" and "token" in request.GET:
        request.session[session_key] = {"uid": request.GET.get("uid", ""), "token": request.GET.get("token", "")}
        # Remove the bearer secret from the visible URL before rendering a form.
        response = redirect(request.path)
    else:
        context = {"verify": purpose == "verify", "success": False, "script_nonce": script_nonce}
        if request.method == "POST":
            serializer = ConfirmInput(data={**request.POST.dict(), **request.session.get(session_key, {})})
            try:
                serializer.is_valid(raise_exception=True)
                confirm_account(serializer.validated_data, purpose)
                request.session.pop(session_key, None)
                context["success"] = True
            except ValidationError as exc:
                context["errors"] = exc.detail
        response = render(request, "email/account_form.html", context)
    # no-referrer can make native form POSTs send Origin: null, failing CSRF.
    # The form URL has already been cleaned; never disclose it cross-origin.
    response["Referrer-Policy"] = "same-origin"
    response["Content-Security-Policy"] = (
        "default-src 'none'; style-src 'unsafe-inline'; "
        f"script-src 'nonce-{script_nonce}'; "
        "form-action 'self'; frame-ancestors 'none'; base-uri 'none'"
    )
    return response
