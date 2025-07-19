import logging

logger = logging.getLogger(__name__)


class AdminLoginDebugMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        is_admin = request.path.startswith("/admin/")
        is_post = request.method == "POST"

        request.session.modified = True
        request.session.save()

        response = self.get_response(request)

        if is_admin and is_post:
            logger.info("=== Middleware: Admin login debug ===")
            logger.info(f"User: {getattr(request, 'user', 'N/A')}")
            logger.info(
                f"Is Authenticated: {getattr(request.user, 'is_authenticated', False)}"
            )
            logger.info(f"Session key: {request.session.session_key}")
            logger.info(f"Session data: {dict(request.session.items())}")

            # 🟡 Теперь форсируем сохранение изменённой сессии
            request.session.modified = True
            request.session.save()

            logger.info(f"Response status: {response.status_code}")
            logger.info(f"Set-Cookie headers: {response.headers.get('Set-Cookie')}")

            logger.info("Response headers:")
            for header, value in response.headers.items():
                logger.info(f"{header}: {value}")

        return response
