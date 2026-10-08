"""Firebase verification and revocation checks for locally issued sessions."""
import logging

import firebase_admin
from firebase_admin import auth
from rest_framework import serializers
from rest_framework.exceptions import APIException

logger = logging.getLogger(__name__)


class FirebaseUnavailable(APIException):
    status_code = 503
    default_detail = "Firebase authentication is temporarily unavailable"


class FirebaseRejected(APIException):
    status_code = 401
    default_detail = "Firebase session unavailable. Please sign in again."


def firebase_project_id():
    try:
        project_id = firebase_admin.get_app().project_id
        if not project_id:
            raise ValueError("Missing project")
        return project_id
    except Exception as exc:
        logger.error("Firebase configuration unavailable (%s)", type(exc).__name__)
        raise FirebaseUnavailable() from None


def verify_firebase_token(token):
    project_id = firebase_project_id()
    try:
        claims = auth.verify_id_token(token, check_revoked=True)
    except (auth.InvalidIdTokenError, auth.RevokedIdTokenError,
            auth.UserDisabledError, auth.UserNotFoundError):
        raise FirebaseRejected("Invalid Firebase token") from None
    except Exception as exc:
        logger.error("Firebase verification unavailable (%s)", type(exc).__name__)
        raise FirebaseUnavailable() from None

    uid = claims.get("uid")
    auth_time = claims.get("auth_time")
    if (not isinstance(uid, str) or not 1 <= len(uid) <= 128
            or type(auth_time) is not int or auth_time <= 0
            or claims.get("aud") != project_id):
        raise FirebaseRejected("Invalid Firebase token")
    if claims.get("email_verified") is not True:
        raise FirebaseRejected("Email missing or not verified")
    try:
        email = serializers.EmailField(max_length=254).run_validation(claims.get("email"))
    except serializers.ValidationError:
        raise FirebaseRejected("Email missing or not verified") from None
    return claims, email.lower()


def check_firebase_session(user, token):
    # Password/Google sessions retain their existing local revocation checks.
    if "firebase_uid" not in token:
        return
    uid = token.get("firebase_uid")
    auth_time = token.get("firebase_auth_time")
    if (not uid or uid != user.firebase_uid or type(auth_time) is not int
            or auth_time <= 0):
        raise FirebaseRejected()
    if token.get("firebase_project_id") != firebase_project_id():
        raise FirebaseRejected()
    try:
        record = auth.get_user(uid)
    except auth.UserNotFoundError:
        raise FirebaseRejected() from None
    except Exception as exc:
        logger.error("Firebase session check unavailable (%s)", type(exc).__name__)
        raise FirebaseUnavailable() from None
    if record.disabled or auth_time * 1000 < record.tokens_valid_after_timestamp:
        raise FirebaseRejected()
