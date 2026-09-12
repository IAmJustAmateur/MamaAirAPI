from drf_spectacular.extensions import OpenApiAuthenticationExtension


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
