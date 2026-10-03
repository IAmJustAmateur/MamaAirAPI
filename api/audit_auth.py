"""Identify the owner of an expired access token for diagnostics only."""
import math
from datetime import datetime, timezone as datetime_timezone

import jwt
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.tokens import AccessToken


def expired_token_owner(request):
    """Return an audit user/metadata, never authenticate or modify the request.

    Only expiration is relaxed. Signature, configured algorithm, issuer,
    audience, iat and nbf are still checked before trusting any claim.
    """
    try:
        authentication = JWTAuthentication()
        header = authentication.get_header(request)
        raw_token = authentication.get_raw_token(header) if header else None
        if not raw_token or len(raw_token) > 8192:
            return None, {}
        backend = AccessToken().get_token_backend()
        payload = jwt.decode(
            raw_token,
            backend.get_verifying_key(raw_token),
            algorithms=[backend.algorithm],
            audience=backend.audience,
            issuer=backend.issuer,
            leeway=backend.get_leeway(),
            options={
                "verify_signature": True,
                "verify_exp": False,
                "verify_aud": backend.audience is not None,
                "require": ["exp", "iat", api_settings.TOKEN_TYPE_CLAIM,
                            api_settings.JTI_CLAIM, api_settings.USER_ID_CLAIM],
            },
        )
        if payload[api_settings.TOKEN_TYPE_CLAIM] != AccessToken.token_type:
            return None, {}
        expiry = payload["exp"]
        if isinstance(expiry, bool) or not isinstance(expiry, (int, float)) or not math.isfinite(expiry):
            return None, {}
        now = timezone.now()
        if expiry > now.timestamp() - backend.get_leeway().total_seconds():
            return None, {}
        expired_at = datetime.fromtimestamp(expiry, tz=datetime_timezone.utc)
        identifier = payload[api_settings.USER_ID_CLAIM]
        if isinstance(identifier, bool) or not isinstance(identifier, (str, int)):
            return None, {}
        user_id = get_user_model().objects.filter(
            **{api_settings.USER_ID_FIELD: identifier}
        ).values_list("pk", flat=True).first()
        if user_id is None:
            return None, {}
        return user_id, {
            "user_source": "expired_access_token",
            "authentication_succeeded": False,
            "token_expired_at": expired_at.isoformat(),
            "token_expired_seconds_ago": max(0, int(now.timestamp() - expiry)),
        }
    except Exception:
        # Malformed tokens, key lookup and DB failures must not lose the audit row
        # or change the original 401. Never log token contents or decoder errors.
        return None, {}
