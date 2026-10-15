"""Public, CSRF-protected proof of ownership followed by explicit deletion."""
import hashlib
import secrets
import time
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import transaction
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.crypto import salted_hmac
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.debug import sensitive_post_parameters, sensitive_variables
from django.views.decorators.http import require_http_methods
from rest_framework.exceptions import APIException
from rest_framework.throttling import BaseThrottle

from api.account_deletion import delete_account
from api.auth_views import verify_id_token
from api.email_auth import account_state, find_user, user_can_authenticate
from api.firebase_auth import verify_firebase_token
from api.models import AccountDeletionGrant

User = get_user_model()
SESSION_KEY = "account_deletion_proof"
INVALID = "We could not verify this account. Check your sign-in details and try again."
EXPIRED = "This confirmation is invalid, expired, or already used. Please sign in again."
LIFETIME = 300


def deletion_state(user):
    return hashlib.sha256(
        f"{account_state(user)}:{user.firebase_uid}:{user.google_sub}".encode()
    ).hexdigest()


def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def allowed_attempt(request):
    # Atomic fixed-window counters work across web workers with the deployment's
    # Redis cache. Hash identities; never place credentials or emails in keys.
    identities = [("ip", BaseThrottle().get_ident(request), 20)]
    if request.POST.get("action") == "password":
        identities.append(("email", request.POST.get("email", "").strip().lower(), 5))
    allowed = True
    for kind, value, limit in identities:
        key = "delete-attempt:" + salted_hmac(kind, value).hexdigest()
        if cache.add(key, 1, timeout=600):
            count = 1
        else:
            try:
                count = cache.incr(key)
            except ValueError:  # The window expired between add and incr.
                count = 1
                cache.add(key, count, timeout=600)
        allowed = allowed and count <= limit
    return allowed


def revoke_proof(request):
    token = request.session.pop(SESSION_KEY, "")
    if token:
        AccountDeletionGrant.objects.filter(token_hash=digest(token)).delete()


@sensitive_variables()
def verify_owner(request):
    action = request.POST.get("action")
    if action == "password":
        email = request.POST.get("email", "")
        password = request.POST.get("password", "")
        if len(email) > 254 or not 1 <= len(password) <= 128:
            return None
        user = find_user(email.strip().lower())
        if not user:
            User().set_password(password)  # Match the password-hashing cost.
            return None
        return user if user.check_password(password) and user_can_authenticate(user) else None

    token = request.POST.get("id_token", "")
    if not 1 <= len(token) <= 16384:
        return None
    if action == "google" and settings.DELETION_GOOGLE_CLIENT_ID:
        try:
            claims = verify_id_token(token)
        except (ValueError, TypeError):
            return None
        nonce = request.session.get("deletion_google_nonce")
        if (claims.get("aud") != settings.DELETION_GOOGLE_CLIENT_ID
                or claims.get("iss") not in {"accounts.google.com", "https://accounts.google.com"}
                or claims.get("email_verified") is not True
                or not nonce or claims.get("nonce") != nonce
                or not isinstance(claims.get("sub"), str) or not claims["sub"]):
            return None
        users = list(User.objects.filter(google_sub=claims["sub"])[:2])
    elif action == "firebase" and settings.DELETION_FIREBASE_CONFIG:
        claims, _ = verify_firebase_token(token)
        if not 0 <= time.time() - claims["auth_time"] <= LIFETIME:
            return None
        users = list(User.objects.filter(firebase_uid=claims["uid"])[:2])
    else:
        return None
    # No linking or account creation here, including on an email match.
    return users[0] if len(users) == 1 and user_can_authenticate(users[0]) else None


@sensitive_variables()
def issue_proof(request, user):
    token = secrets.token_urlsafe(32)
    with transaction.atomic():
        current = User.objects.select_for_update().filter(pk=user.pk).first()
        if not current or deletion_state(current) != deletion_state(user):
            return False
        AccountDeletionGrant.objects.filter(expires_at__lte=timezone.now()).delete()
        AccountDeletionGrant.objects.create(token_hash=digest(token), user=current,
            account_state=deletion_state(current), expires_at=timezone.now() + timedelta(seconds=LIFETIME))
    request.session.cycle_key()
    request.session[SESSION_KEY] = token
    request.session.pop("deletion_google_nonce", None)
    return True


@sensitive_variables()
def confirm_deletion(request):
    token = request.session.get(SESSION_KEY, "")
    if not token:
        return False
    # Lock the user first, consistently with mobile deletion; then lock proof.
    user_id = AccountDeletionGrant.objects.filter(token_hash=digest(token)).values_list("user_id", flat=True).first()
    with transaction.atomic():
        user = User.objects.select_for_update().filter(pk=user_id).first()
        grant = AccountDeletionGrant.objects.select_for_update().filter(token_hash=digest(token)).first()
        if (not user or not grant or grant.expires_at <= timezone.now()
                or not user_can_authenticate(user) or grant.account_state != deletion_state(user)):
            return False
        delete_account(user.pk)
    request.session.flush()
    return True


@sensitive_post_parameters()
@never_cache
@csrf_protect
@require_http_methods(["GET", "POST"])
def delete_account_page(request):
    context = {"script_nonce": secrets.token_urlsafe(16), "success": False}
    status = 200
    if request.method == "POST":
        if not allowed_attempt(request):
            context["error"] = "Too many attempts. Please try again in 10 minutes."
            status = 429
        elif request.POST.get("action") == "confirm":
            if request.POST.get("confirmation") != "DELETE":
                context["error"] = "Type DELETE exactly to confirm."
                status = 400
            elif confirm_deletion(request):
                context["success"] = True
            else:
                revoke_proof(request)
                context["error"] = EXPIRED
                status = 400
        elif request.POST.get("action") == "cancel":
            revoke_proof(request)
            return redirect("delete-account-page")
        else:
            revoke_proof(request)
            try:
                user = verify_owner(request)
                if user and issue_proof(request, user):
                    return redirect("delete-account-page")
                context["error"] = INVALID
                status = 400
            except APIException as exc:
                context["error"] = INVALID if exc.status_code < 500 else "Sign-in is temporarily unavailable. Please try again later."
                status = 400 if exc.status_code < 500 else 503
            except Exception:
                # Provider/network failures must not echo tokens or exception text.
                context["error"] = "Sign-in is temporarily unavailable. Please try again later."
                status = 503
    token = request.session.get(SESSION_KEY, "")
    grant = AccountDeletionGrant.objects.filter(token_hash=digest(token), expires_at__gt=timezone.now()).select_related("user").first() if token else None
    if token and not grant:
        revoke_proof(request)
        context.setdefault("error", EXPIRED)
    context["confirm"] = bool(grant)
    if grant:
        context["account_email"] = grant.user.email
    if not context["confirm"] and not context["success"]:
        nonce = request.session.setdefault("deletion_google_nonce", secrets.token_urlsafe(32))
        context["google_config"] = {"client_id": settings.DELETION_GOOGLE_CLIENT_ID, "nonce": nonce}
        context["firebase_config"] = settings.DELETION_FIREBASE_CONFIG
    response = render(request, "email/delete_account.html", context, status=status)
    response["Referrer-Policy"] = "same-origin"
    response["Cross-Origin-Opener-Policy"] = "same-origin-allow-popups"
    response["Content-Security-Policy"] = (
        "default-src 'none'; style-src 'unsafe-inline' https://accounts.google.com; "
        f"script-src 'nonce-{context['script_nonce']}' https://accounts.google.com/gsi/client https://www.gstatic.com/firebasejs/ https://apis.google.com/; "
        "connect-src 'self' https://accounts.google.com https://identitytoolkit.googleapis.com https://securetoken.googleapis.com; "
        "frame-src https://accounts.google.com https://*.firebaseapp.com; "
        "img-src 'self' https://*.googleusercontent.com; form-action 'self'; frame-ancestors 'none'; base-uri 'none'"
    )
    if status == 429:
        response["Retry-After"] = "600"
    return response
