import tempfile
from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.db import transaction
from django.test import TestCase, override_settings
from django.utils import timezone

from api.account_deletion import cleanup_after_commit, cleanup_file, delete_account
from api.email_auth import account_state
from api.models import AccountFileCleanup
from api import models
from api.tasks import send_account_email

User = get_user_model()


class AccountCleanupTests(TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.settings_override = override_settings(MEDIA_ROOT=self.temp.name)
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        self.user = User.objects.create_user(email="cleanup@example.com", password="test-password")
        self.user.avatar.save("avatar.png", ContentFile(b"avatar"), save=True)
        self.name = self.user.avatar.name
        self.storage = User._meta.get_field("avatar").storage

    def test_committed_intent_survives_lost_callback_and_retries(self):
        delete_account(self.user.pk)  # TestCase keeps on_commit callbacks pending.
        self.assertTrue(self.storage.exists(self.name))
        intent = AccountFileCleanup.objects.get()
        with patch.object(self.storage, "delete", side_effect=OSError("storage secret")):
            cleanup_file(intent.pk)
        intent.refresh_from_db()
        self.assertEqual(intent.attempts, 1)
        self.assertEqual(intent.error_type, "OSError")
        self.assertGreater(intent.next_attempt_at, timezone.now())
        AccountFileCleanup.objects.update(next_attempt_at=timezone.now() - timedelta(seconds=1))
        call_command("retry_account_file_cleanup", stdout=StringIO())
        self.assertFalse(self.storage.exists(self.name))
        self.assertFalse(AccountFileCleanup.objects.exists())
        cleanup_file(intent.pk)  # Retry after successful acknowledgement.

    def test_storage_failure_does_not_fail_account_deletion(self):
        with patch.object(self.storage, "delete", side_effect=OSError()):
            with self.captureOnCommitCallbacks(execute=True):
                self.assertTrue(delete_account(self.user.pk))
        self.assertFalse(User.objects.filter(pk=self.user.pk).exists())
        self.assertEqual(AccountFileCleanup.objects.get().attempts, 1)

    def test_callback_database_failure_leaves_intent(self):
        delete_account(self.user.pk)
        intent = AccountFileCleanup.objects.get()
        with patch("api.account_deletion.cleanup_file", side_effect=RuntimeError("database unavailable")):
            cleanup_after_commit(intent.pk)
        self.assertTrue(AccountFileCleanup.objects.filter(pk=intent.pk).exists())
        cleanup_file(intent.pk)
        self.assertFalse(self.storage.exists(self.name))

    def test_rollback_preserves_account_file_and_discards_intent(self):
        with self.captureOnCommitCallbacks(execute=True):
            with self.assertRaises(RuntimeError):
                with transaction.atomic():
                    delete_account(self.user.pk)
                    raise RuntimeError("rollback")
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())
        self.assertTrue(self.storage.exists(self.name))
        self.assertFalse(AccountFileCleanup.objects.exists())

    def test_missing_file_and_duplicate_delete_are_idempotent(self):
        self.storage.delete(self.name)
        with self.captureOnCommitCallbacks(execute=True):
            self.assertTrue(delete_account(self.user.pk))
        self.assertFalse(delete_account(self.user.pk))
        self.assertFalse(AccountFileCleanup.objects.exists())

    def test_shared_file_is_preserved_until_no_account_references_it(self):
        other = User.objects.create_user(email="shared@example.com", avatar=self.name)
        with self.captureOnCommitCallbacks(execute=True):
            delete_account(self.user.pk)
        self.assertTrue(self.storage.exists(self.name))
        self.assertTrue(User.objects.filter(pk=other.pk).exists())
        intent = AccountFileCleanup.objects.get()
        other.avatar = ""
        other.save(update_fields=["avatar"])
        cleanup_file(intent.pk)
        self.assertFalse(self.storage.exists(self.name))

    def test_other_user_files_shared_paths_and_external_urls_are_never_deleted(self):
        for name in ("avatars/user_999/" + "a" * 32 + ".png", "avatars/shared.png",
                     "https://example.com/photo.png", f"avatars/user_{self.user.pk}/../shared.png"):
            user = User.objects.create_user(email=f"user{User.objects.count()}@example.com", avatar=name)
            with patch.object(self.storage, "delete") as storage_delete:
                with self.captureOnCommitCallbacks(execute=True):
                    delete_account(user.pk)
                storage_delete.assert_not_called()
        self.assertFalse(AccountFileCleanup.objects.exists())

    def test_delayed_email_does_not_recreate_deleted_or_reregistered_user(self):
        email, state = self.user.email, account_state(self.user)
        delete_account(self.user.pk)
        with patch("api.tasks.EmailMultiAlternatives.send") as send:
            send_account_email.run(email, "reset", state)
            self.assertFalse(User.objects.filter(email=email).exists())
            replacement = User.objects.create_user(email=email, password="new-password")
            send_account_email.run(email, "reset", state)
            send.assert_not_called()
        replacement.refresh_from_db()
        self.assertTrue(replacement.check_password("new-password"))

    def test_email_already_in_flight_cannot_recreate_user(self):
        email, state = self.user.email, account_state(self.user)
        with patch("api.tasks.EmailMultiAlternatives.send", side_effect=lambda **kwargs: delete_account(self.user.pk)):
            send_account_email.run(email, "reset", state)
        self.assertFalse(User.objects.filter(email=email).exists())

    def test_owned_graph_removed_other_user_and_shared_catalogs_preserved(self):
        other = User.objects.create_user(email="kept@example.com")
        today, now = timezone.localdate(), timezone.now()
        task = models.DailyTask.objects.create(code="deletion-test-task", title="Task")
        mommy = models.MommySymptom.objects.create(code="deletion-mommy", name="Mommy")
        baby = models.BabySymptom.objects.create(code="deletion-baby", name="Baby")
        wellbeing = models.Wellbeing.objects.create(code="deletion-mood", title="Mood", kind="mood")

        def graph(user):
            lifestyle, _ = models.UserLifeStyle.objects.get_or_create(user=user)
            snapshot = models.HealthInsightSnapshot.objects.create(user=user)
            plan = models.DailyPlan.objects.create(user=user, local_date=today, timezone="UTC")
            checklist = models.GeneratedSymptomChecklist.objects.create(user=user,
                checklist_type="mommy", local_date=today, algorithm_version="test")
            response = models.SymptomChecklistResponse.objects.create(user=user,
                checklist=checklist, checklist_type="mommy", local_date=today, recorded_at=now)
            log = models.UserWellbeingLog.objects.create(user=user, date=today)
            log.moods.add(wellbeing)
            return [lifestyle, snapshot, plan, checklist, response, log,
                models.UserMommySymptoms.objects.create(user=user, symptom=mommy),
                models.UserBabySymptoms.objects.create(user=user, symptom=baby),
                models.Movement.objects.create(user=user, latitude=1, longitude=2, timestamp=now),
                models.AirExposureLog.objects.create(user=user, latitude=1, longitude=2, timestamp=now),
                models.Exposure.objects.create(user=user, exposure_level=1),
                models.DailyExposure.objects.create(user=user, date=today, exposure_level="Clean"),
                models.WeeklyExposure.objects.create(user=user, pregnancy_week=10, exposure_level="Clean"),
                models.RecommendationCompletion.objects.create(user=user, snapshot=snapshot, rule_id="test", dimension="diet"),
                models.DailyCheckin.objects.create(user=user, date=today),
                models.UserDailyTaskCompletion.objects.create(user=user, task=task, date=today),
                models.DailyAction.objects.create(plan=plan, stable_key="test", domain="activity", role="primary",
                    title="Test", source_type="task", source_task_id=task.pk),
                models.GeneratedSymptomChecklistItem.objects.create(checklist=checklist, symptom_id_snapshot=mommy.pk,
                    symptom_code=mommy.code, display_name="Test", position=0),
                models.SymptomChecklistResponseItem.objects.create(response=response, symptom_code=mommy.code,
                    display_name="Test", position=0, status="reported")]

        removed, kept = graph(self.user), graph(other)
        delete_account(self.user.pk)
        for row in removed:
            self.assertFalse(type(row).objects.filter(pk=row.pk).exists(), type(row).__name__)
        for row in kept + [task, mommy, baby, wellbeing, other]:
            self.assertTrue(type(row).objects.filter(pk=row.pk).exists(), type(row).__name__)
