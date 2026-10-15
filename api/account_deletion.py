"""Account deletion shared by the mobile API and the public confirmation page."""
import logging
import re
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken

from api.models import AccountFileCleanup, AuditLog, SymptomChecklistResponse

logger = logging.getLogger(__name__)
User = get_user_model()


def is_owned_avatar(name, user_id):
    # Only generated upload names are owned. Legacy/shared paths, external URLs,
    # traversal and other users' directories must never reach storage.delete.
    return bool(re.fullmatch(rf"avatars/user_{user_id}/[a-f0-9]{{32}}\.[a-z0-9]+", name))


def cleanup_file(intent_id):
    with transaction.atomic():
        intent = AccountFileCleanup.objects.select_for_update().filter(pk=intent_id).first()
        if not intent:
            return
        try:
            if not is_owned_avatar(intent.file_name, intent.owner_id):
                raise ValueError("Unowned file")
            if User.objects.filter(avatar=intent.file_name).exists():
                raise ValueError("Referenced file")
            User._meta.get_field("avatar").storage.delete(intent.file_name)
        except Exception as exc:
            intent.attempts += 1
            intent.error_type = type(exc).__name__[:100]
            intent.next_attempt_at = timezone.now() + timedelta(seconds=min(86400, 60 * 2 ** min(intent.attempts, 10)))
            intent.save(update_fields=["attempts", "error_type", "next_attempt_at"])
            logger.warning("Account file cleanup deferred (%s)", type(exc).__name__)
        else:
            intent.delete()


def cleanup_after_commit(intent_id):
    try:
        cleanup_file(intent_id)
    except Exception as exc:
        # The intent is already committed. A database/process failure here does
        # not undo account deletion; the independent sweeper finds it later.
        logger.error("Account cleanup callback failed (%s)", type(exc).__name__)


def delete_account(user_id):
    # The same lock serializes web confirmation and mobile deletion. Never save
    # a stale user instance supplied by an authenticated request.
    with transaction.atomic():
        user = User.objects.select_for_update().filter(pk=user_id).first()
        if user is None:
            return False
        avatar_name = user.avatar.name if user.avatar else None
        intent = None
        if avatar_name and is_owned_avatar(avatar_name, user.pk):
            intent, _ = AccountFileCleanup.objects.get_or_create(
                file_name=avatar_name, defaults={"owner_id": user.pk})
        SymptomChecklistResponse.objects.filter(user=user).delete()
        OutstandingToken.objects.filter(user=user).delete()
        AuditLog.objects.filter(user=user).delete()
        user.delete()

        if intent:
            transaction.on_commit(lambda: cleanup_after_commit(intent.pk))
    return True
