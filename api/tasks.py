import logging
import smtplib
from urllib.parse import urlencode

from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

from .email_auth import account_state, encoded_uid, find_user, reset_tokens, verification_tokens

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, ignore_result=True)
def send_account_email(self, email, purpose, expected_state):
    user = find_user(email)
    if purpose not in {"verify", "reset"} or not user or not user.is_active:
        return
    if account_state(user) != expected_state:
        return
    if user.email_verification_pending != (purpose == "verify"):
        return
    generator = verification_tokens if purpose == "verify" else reset_tokens
    path = "verify-email" if purpose == "verify" else "reset-password"
    context = {
        "name": user.name or "there",
        "action": "Confirm email and set password" if purpose == "verify" else "Reset password",
        "url": f"{settings.AUTH_PUBLIC_URL}/{path}?" + urlencode({"uid": encoded_uid(user), "token": generator.make_token(user)}),
        "support_email": settings.SUPPORT_EMAIL,
    }
    message = EmailMultiAlternatives(
        subject=f"MamaAir: {context['action']}",
        body=render_to_string("email/account.txt", context),
        from_email=settings.DEFAULT_FROM_EMAIL, to=[user.email],
        reply_to=[settings.SUPPORT_EMAIL],
    )
    message.attach_alternative(render_to_string("email/account.html", context), "text/html")
    try:
        message.send(fail_silently=False)
    except smtplib.SMTPResponseException as exc:
        if 400 <= exc.smtp_code < 500:
            raise self.retry(exc=RuntimeError("Temporary SMTP failure"), countdown=2 ** (self.request.retries + 1))
        logger.error("Account email rejected by SMTP: code=%s", exc.smtp_code)
        raise RuntimeError("Permanent SMTP failure") from None
    except (OSError, smtplib.SMTPServerDisconnected):
        raise self.retry(exc=RuntimeError("SMTP connection unavailable"), countdown=2 ** (self.request.retries + 1))
