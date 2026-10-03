"""Bounded diagnostic request logging. Never persist raw/non-JSON bodies."""
import ipaddress
import json
import logging
import re
import time
import traceback
import uuid

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from django.utils.deprecation import MiddlewareMixin

from api.models import AuditLog

logger = logging.getLogger(__name__)
REDACTED = "[redacted]"
SENSITIVE = re.compile(
    r"password|passwd|secret|token|authorization|cookie|credential|"
    r"latitude|longitude|coordinate|location|position|geohash|h3cell|"
    r"^(lat|lon|lng|gps|geo|point|geometry|access|refresh|code|key|apikey)$",
    re.I,
)
SUCCESS_ACTIONS = {"symptoms-mommy-selection", "symptoms-baby-selection"}
SAFE_RESPONSE_DIAGNOSTICS = {
    "code": {"token_not_valid", "authentication_failed", "not_authenticated",
             "permission_denied", "user_not_found", "user_inactive", "password_changed"},
    "token_type": {"access", "refresh", "sliding"},
    "token_class": {"AccessToken", "RefreshToken", "SlidingToken", "UntypedToken"},
}


def safe_diagnostic(key, value, diagnostics):
    return diagnostics and isinstance(value, str) and value in SAFE_RESPONSE_DIAGNOSTICS.get(key, ())


def sensitive(key):
    return bool(SENSITIVE.search(re.sub(r"[^a-z0-9]", "", str(key).lower())))


def sanitize(value, secrets=(), depth=0, diagnostics=False):
    if depth > 20:
        return "[depth limit]"
    if isinstance(value, dict):
        return {str(k): REDACTED if sensitive(k) and not safe_diagnostic(k, v, diagnostics)
                else sanitize(v, secrets, depth + 1, diagnostics)
                for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize(v, secrets, depth + 1, diagnostics) for v in value]
    if isinstance(value, str):
        for secret in secrets:
            if secret:
                value = value.replace(secret, REDACTED)
        # Free text can contain echoed JSON, bearer tokens or coordinate pairs.
        value = re.sub(r"(?i)bearer\s+\S+", REDACTED, value)
        value = re.sub(r"eyJ[\w-]+\.[\w-]+\.[\w-]+", REDACTED, value)
        value = re.sub(r"(?i)(password|token|secret|lat(?:itude)?|lon(?:gitude)?|lng)"
                       r"[\"']?\s*[:=]\s*[^\s,;}]+", REDACTED, value)
        value = re.sub(r"-?\d{1,3}\.\d+\s*[,; ]\s*-?\d{1,3}\.\d+", REDACTED, value)
        return value
    return value


def collect_secrets(value, diagnostics=False):
    result = []
    if isinstance(value, dict):
        for key, item in value.items():
            if sensitive(key) and not safe_diagnostic(key, item, diagnostics):
                def leaves(v):
                    if isinstance(v, dict):
                        for child in v.values():
                            yield from leaves(child)
                    elif isinstance(v, list):
                        for child in v:
                            yield from leaves(child)
                    elif v is not None:
                        yield str(v)
                result.extend(leaves(item))
            else:
                result.extend(collect_secrets(item, diagnostics))
    elif isinstance(value, list):
        for item in value:
            result.extend(collect_secrets(item, diagnostics))
    return sorted(set(result), key=len, reverse=True)


class AuditLogMiddleware(MiddlewareMixin):
    def process_request(self, request):
        if not settings.AUDIT_LOG_ENABLED or not request.path.startswith("/api/"):
            return
        request.audit_id = uuid.uuid4()
        request.audit_started = time.monotonic()
        request.audit_timestamp = timezone.now()
        request.audit_metadata = {}
        request.audit_body = None
        # Do not consume uploads or large bodies; preserve normal request parsing.
        try:
            length = int(request.META.get("CONTENT_LENGTH") or 0)
            if request.content_type == "application/json" and 0 < length <= settings.AUDIT_LOG_MAX_BODY_BYTES:
                request.audit_body = json.loads(request.body)
            elif length or request.content_type:
                request.audit_metadata["request_body_omitted"] = "size_or_content_type"
        except Exception:
            request.audit_metadata["request_body_omitted"] = "invalid_json"

    def process_exception(self, request, exception):
        if hasattr(request, "audit_id"):
            request.audit_error_type = type(exception).__name__
            # Frame locations only: exception text, source lines and locals may contain secrets.
            request.audit_traceback = "\n".join(
                f"{frame.filename}:{frame.lineno} in {frame.name}"
                for frame in traceback.extract_tb(exception.__traceback__)
            )[:settings.AUDIT_LOG_MAX_BODY_BYTES]

    def process_response(self, request, response):
        if not hasattr(request, "audit_id"):
            return response
        response["X-Request-ID"] = str(request.audit_id)
        match = request.resolver_match
        action = match.url_name if match else ""
        data = getattr(response, "data", None)
        movement_errors = action in {"movements-upload", "movements-upload-json"} and isinstance(data, dict) and (
            data.get("errors") or data.get("exposure_errors")
        )
        if response.status_code < 400 and not movement_errors and not (
            action in SUCCESS_ACTIONS and request.method in {"POST", "PUT", "PATCH"}
        ):
            return response
        try:
            self.write_log(request, response, action)
        except Exception:
            # Do not log exception text: database errors may embed the rejected payload.
            logger.error("Unable to persist request audit log", extra={"request_id": str(request.audit_id)})
        return response

    def write_log(self, request, response, action):
        metadata = request.audit_metadata
        query = dict(request.GET.lists())
        secrets = collect_secrets(request.audit_body) + collect_secrets(query)
        for name in ("HTTP_AUTHORIZATION", "HTTP_COOKIE"):
            if request.META.get(name):
                secrets.append(request.META[name])

        def bounded(value, field):
            value = sanitize(value, secrets, diagnostics=field == "response_body")
            if len(json.dumps(value, ensure_ascii=False).encode("utf-8")) > settings.AUDIT_LOG_MAX_BODY_BYTES:
                metadata[field + "_omitted"] = "size_limit"
                return None
            return value

        if request.resolver_match and request.resolver_match.kwargs:
            metadata["path_params"] = bounded(
                {key: str(value) for key, value in request.resolver_match.kwargs.items()}, "path_params"
            )

        body = None
        if response.streaming:
            metadata["response_body_omitted"] = "streaming"
        elif "application/json" in response.get("Content-Type", ""):
            if len(response.content) <= settings.AUDIT_LOG_MAX_BODY_BYTES:
                try:
                    body = json.loads(response.content)
                    secrets.extend(collect_secrets(body, diagnostics=True))
                except (ValueError, UnicodeError, RecursionError):
                    metadata["response_body_omitted"] = "invalid_json"
            else:
                metadata["response_body_omitted"] = "size_limit"
        else:
            metadata["response_body_omitted"] = "non_json"
        if "request_body_omitted" in metadata:
            # A parser can echo secrets from malformed JSON, CSV or an oversized body.
            # Without inspecting that body we cannot safely retain its error text.
            def omit_text(value):
                if isinstance(value, dict):
                    return {key: item if safe_diagnostic(key, item, True) else omit_text(item)
                            for key, item in value.items()}
                if isinstance(value, list):
                    return [omit_text(item) for item in value]
                return "[text omitted: request body unavailable]" if isinstance(value, str) else value
            body = omit_text(body)
            metadata["response_text_omitted"] = "request_body_unavailable"
        try:
            ip = str(ipaddress.ip_address(request.META.get("REMOTE_ADDR", "")))
        except ValueError:
            ip = None
        user = getattr(request, "user", None)
        # An account-deletion endpoint may have deleted the authenticated row.
        user_id = user.pk if user and user.is_authenticated else None
        if user_id and not get_user_model().objects.filter(pk=user_id).exists():
            user_id = None
        if user_id is None and response.status_code == 401:
            from api.audit_auth import expired_token_owner

            user_id, attribution = expired_token_owner(request)
            metadata.update(attribution)
        with transaction.atomic():
            AuditLog.objects.create(
                timestamp=request.audit_timestamp, request_id=request.audit_id,
                user_id=user_id, action=action or "", method=request.method[:16],
                # Route templates avoid retaining credentials/coordinates in arbitrary URL segments.
                path="/" + request.resolver_match.route if request.resolver_match else "/api/[unresolved]",
                status_code=response.status_code,
                duration_ms=max(0, int((time.monotonic() - request.audit_started) * 1000)),
                ip_address=ip, user_agent=sanitize(request.META.get("HTTP_USER_AGENT", ""), secrets)[:1024],
                request_headers=bounded({key: request.headers[key] for key in
                    ("Content-Type", "Accept", "Accept-Language") if key in request.headers}, "request_headers") or {},
                query_params=bounded(query, "query_params") or {},
                request_body=bounded(request.audit_body, "request_body"),
                response_body=bounded(body, "response_body"),
                error_type=getattr(request, "audit_error_type", ""),
                traceback=getattr(request, "audit_traceback", ""), metadata=metadata,
            )
