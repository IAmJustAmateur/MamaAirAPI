from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from api.models import AuditLog


class Command(BaseCommand):
    help = "Delete request audit logs older than AUDIT_LOG_RETENTION_DAYS (run daily)."

    def handle(self, *args, **options):
        days = settings.AUDIT_LOG_RETENTION_DAYS
        if days < 1:
            raise CommandError("AUDIT_LOG_RETENTION_DAYS must be positive")
        cutoff = timezone.now() - timedelta(days=days)
        total = 0
        while True:
            ids = list(AuditLog.objects.filter(timestamp__lt=cutoff).values_list("pk", flat=True)[:1000])
            if not ids:
                break
            count, _ = AuditLog.objects.filter(pk__in=ids).delete()
            total += count
        self.stdout.write(f"Deleted {total} audit logs")
