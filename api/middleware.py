import logging

logger = logging.getLogger(__name__)


class AdminLoginDebugMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        is_admin = request.path.startswith("/admin/")
        is_post = request.method == "POST"

        response = self.get_response(request)

        if is_admin and is_post:
            logger.info("=== Middleware: Admin login debug ===")
            logger.info(f"User: {getattr(request, 'user', 'N/A')}")
            logger.info(
                f"Is Authenticated: {getattr(request.user, 'is_authenticated', False)}"
            )
            logger.info(f"Session key: {request.session.session_key}")
            logger.info(f"Session data: {dict(request.session.items())}")
            logger.info(f"Response status: {response.status_code}")
            logger.info(f"Set-Cookie headers: {response.headers.get('Set-Cookie')}")

        return response
