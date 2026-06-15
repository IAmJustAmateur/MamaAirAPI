def hide_legacy_auth_endpoints(endpoints):
    """Hide non-Google authentication endpoints from the public mobile schema."""
    hidden_paths = {
        "/api/auth/register/",
        "/api/auth/token/",
        "/api/auth/firebase/",
        "/api/auth/password-change/",
    }
    return [
        (path, path_regex, method, callback)
        for path, path_regex, method, callback in endpoints
        if path not in hidden_paths
    ]
