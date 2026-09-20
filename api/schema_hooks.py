from drf_spectacular.extensions import OpenApiAuthenticationExtension
from drf_spectacular.openapi import AutoSchema


class DeleteRequestBodyAutoSchema(AutoSchema):
    """Expose an explicitly documented DELETE body in the OpenAPI operation."""

    def _get_request_body(self, direction="request"):
        if self.method != "DELETE":
            return super()._get_request_body(direction)

        # drf-spectacular intentionally limits bodies to POST, PUT and PATCH.
        # This endpoint already has a JSON DELETE contract, so reuse the normal
        # request serializer mapping only while building this operation.
        self.method = "POST"
        try:
            return super()._get_request_body(direction)
        finally:
            self.method = "DELETE"


class LoggingJWTAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = "api.authentication.LoggingJWTAuthentication"
    name = "jwtAuth"

    def get_security_definition(self, auto_schema):
        return {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
        }


def hide_non_mobile_endpoints(endpoints):
    """Hide internal and legacy endpoints from the public mobile schema."""
    hidden_paths = {
        "/api/auth/register/",
        "/api/auth/token/",
        "/api/auth/firebase/",
    }
    hidden_prefixes = (
        "/api/debug/",
        "/demo/",
    )
    return [
        (path, path_regex, method, callback)
        for path, path_regex, method, callback in endpoints
        if path not in hidden_paths
        and not any(path.startswith(prefix) for prefix in hidden_prefixes)
    ]
