# api/permissions.py

import secrets

from rest_framework.permissions import BasePermission
from django.conf import settings


class HasValidRegistrationAPIKey(BasePermission):
    message = "Invalid or missing API key."

    def has_permission(self, request, view):
        configured_key = settings.REGISTRATION_API_KEY
        provided_key = request.headers.get("X-API-Key")
        if not configured_key or not provided_key:
            return False
        return secrets.compare_digest(provided_key, configured_key)
