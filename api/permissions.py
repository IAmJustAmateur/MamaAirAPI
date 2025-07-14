# api/permissions.py

from rest_framework.permissions import BasePermission
from django.conf import settings


class HasValidRegistrationAPIKey(BasePermission):
    message = "Invalid or missing API key."

    def has_permission(self, request, view):
        api_key = request.headers.get("X-API-Key")
        return api_key == settings.REGISTRATION_API_KEY
