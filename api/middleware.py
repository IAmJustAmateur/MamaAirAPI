import logging

logger = logging.getLogger(__name__)


class AdminLoginDebugMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        is_admin = request.path.startswith("/admin/")
        is_post = request.method == "POST"
        if is_admin and is_post:
            logger.info("=== Admin login attempt ===")
            logger.info(f"User: {request.user}")
            logger.info(f"Is Authenticated: {request.user.is_authenticated}")
            logger.info(f"Session key: {request.session.session_key}")
            logger.info(f"Session data: {dict(request.session.items())}")

        response = self.get_response(request)

        if is_admin and is_post:
            logger.info("=== Admin login response ===")
            logger.info(f"Response status: {response.status_code}")
            logger.info(f"Set-Cookie headers: {response.headers.get('Set-Cookie')}")

        return response
