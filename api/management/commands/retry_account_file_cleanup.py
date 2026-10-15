"""Drain durable file cleanup intents; no broker or email worker dependency."""
import time

from django.core.management.base import BaseCommand
from django.utils import timezone

from api.account_deletion import cleanup_file
from api.models import AccountDeletionGrant, AccountFileCleanup


class Command(BaseCommand):
    help = "Retry due account file cleanup intents (use --loop for a dedicated worker)."

    def add_arguments(self, parser):
        parser.add_argument("--loop", action="store_true")

    def handle(self, *args, **options):
        while True:
            ids = list(AccountFileCleanup.objects.filter(next_attempt_at__lte=timezone.now())
                       .order_by("next_attempt_at").values_list("pk", flat=True)[:100])
            for intent_id in ids:
                cleanup_file(intent_id)
            AccountDeletionGrant.objects.filter(expires_at__lte=timezone.now()).delete()
            self.stdout.write(f"Account cleanup checked={len(ids)} pending={AccountFileCleanup.objects.count()}")
            if not options["loop"]:
                return
            time.sleep(60)
