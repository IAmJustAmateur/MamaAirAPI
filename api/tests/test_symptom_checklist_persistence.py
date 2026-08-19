from datetime import datetime, timedelta, timezone as datetime_timezone
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from api.models import (
    BabySymptom,
    GeneratedSymptomChecklist,
    MommySymptom,
    SYMPTOM_CHECKLIST_BABY,
    SYMPTOM_CHECKLIST_MOMMY,
    SYMPTOM_STATUS_NOT_ANSWERED,
    SYMPTOM_STATUS_NOT_REPORTED,
    SYMPTOM_STATUS_REPORTED,
    SymptomChecklistResponse,
    UserLifeStyle,
    UserMommySymptoms,
)
from recommendations.services.symptom_monitoring import (
    get_or_create_daily_checklist,
    local_date_for_user,
)


User = get_user_model()


class SymptomChecklistServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="checklist-service@example.com",
            password="test-pass",
            timezone="Pacific/Kiritimati",
        )
        self.symptom = MommySymptom.objects.create(name="Service headache")

    def test_symptom_code_is_generated_once_and_is_not_name_dependent(self):
        self.assertEqual(self.symptom.code, "mommy.service_headache")

        self.symptom.name = "Renamed symptom"
        self.symptom.save()

        self.assertEqual(self.symptom.code, "mommy.service_headache")

    def test_one_checklist_per_user_type_and_local_day(self):
        first_instant = datetime(2026, 8, 19, 9, tzinfo=datetime_timezone.utc)
        same_local_day = first_instant + timedelta(minutes=30)

        with patch(
            "recommendations.services.symptom_monitoring.generate_symptoms",
            return_value=[self.symptom],
        ) as generate:
            first, first_created = get_or_create_daily_checklist(
                self.user,
                SYMPTOM_CHECKLIST_MOMMY,
                generated_at=first_instant,
            )
            second, second_created = get_or_create_daily_checklist(
                self.user,
                SYMPTOM_CHECKLIST_MOMMY,
                generated_at=same_local_day,
            )

        self.assertTrue(first_created)
        self.assertFalse(second_created)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(generate.call_count, 1)
        self.assertEqual(first.algorithm_version, "risk-priority-v1")
        self.assertEqual(first.items.get().status, SYMPTOM_STATUS_NOT_ANSWERED)

    def test_user_timezone_determines_local_date(self):
        instant = datetime(2026, 8, 19, 12, 30, tzinfo=datetime_timezone.utc)
        self.assertEqual(local_date_for_user(self.user, instant).isoformat(), "2026-08-20")

        self.user.timezone = "Invalid/Timezone"
        self.user.save(update_fields=["timezone"])
        self.assertEqual(local_date_for_user(self.user, instant).isoformat(), "2026-08-19")


class SymptomChecklistAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="checklist-api@example.com",
            password="test-pass",
            timezone="UTC",
        )
        UserLifeStyle.objects.create(user=self.user)
        self.other_user = User.objects.create_user(
            email="other-checklist-api@example.com",
            password="test-pass",
            timezone="UTC",
        )
        self.mommy_1 = MommySymptom.objects.create(name="API headache")
        self.mommy_2 = MommySymptom.objects.create(name="API dizziness")
        self.baby_1 = BabySymptom.objects.create(name="API reduced movement")
        self.client.force_authenticate(self.user)
        self.mommy_checklist_url = reverse("symptoms-mommy-checklist")
        self.mommy_selection_url = reverse("symptoms-mommy-selection")
        self.baby_checklist_url = reverse("symptoms-baby-checklist")
        self.baby_selection_url = reverse("symptoms-baby-selection")

    def _get_mommy_checklist(self):
        with patch(
            "recommendations.services.symptom_monitoring.generate_symptoms",
            return_value=[self.mommy_1, self.mommy_2],
        ):
            return self.client.get(self.mommy_checklist_url)

    def test_repeated_get_returns_same_checklist_and_snapshot(self):
        first = self._get_mommy_checklist()
        self.assertEqual(first.status_code, 200, first.data)

        self.mommy_1.name = "Renamed after presentation"
        self.mommy_1.save()
        second = self._get_mommy_checklist()

        self.assertEqual(first.data, second.data)
        self.assertEqual(
            first.data["symptoms"][0],
            {
                "id": self.mommy_1.pk,
                "code": "mommy.api_headache",
                "name": "API headache",
            },
        )

    def test_omitted_checklist_id_is_automatically_associated(self):
        checklist_response = self._get_mommy_checklist()

        response = self.client.post(
            self.mommy_selection_url,
            {"symptom_ids": [self.mommy_1.pk]},
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(
            str(response.data["checklist_id"]),
            str(checklist_response.data["checklist_id"]),
        )
        event = SymptomChecklistResponse.objects.get()
        self.assertIsNotNone(event.checklist_id)
        statuses = {
            item.symptom_code: item.status for item in event.items.order_by("position")
        }
        self.assertEqual(statuses["mommy.api_headache"], SYMPTOM_STATUS_REPORTED)
        self.assertEqual(statuses["mommy.api_dizziness"], SYMPTOM_STATUS_NOT_REPORTED)

    def test_explicit_checklist_id_is_optional_but_supported(self):
        checklist_response = self._get_mommy_checklist()
        response = self.client.post(
            self.mommy_selection_url,
            {
                "symptom_ids": [self.mommy_2.pk],
                "checklist_id": checklist_response.data["checklist_id"],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(
            str(response.data["checklist_id"]),
            str(checklist_response.data["checklist_id"]),
        )

    def test_post_without_prior_get_keeps_legacy_flow_without_inventing_items(self):
        response = self.client.post(
            self.mommy_selection_url,
            {"symptom_ids": [self.mommy_1.pk]},
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertNotIn("checklist_id", response.data)
        event = SymptomChecklistResponse.objects.get()
        self.assertIsNone(event.checklist_id)
        self.assertEqual(event.items.count(), 0)
        self.assertEqual(event.reported_symptom_codes, ["mommy.api_headache"])
        self.assertTrue(
            UserMommySymptoms.objects.filter(
                user=self.user, symptom=self.mommy_1
            ).exists()
        )

    def test_repeated_post_preserves_events_and_replaces_current_selection(self):
        checklist_response = self._get_mommy_checklist()
        checklist_id = checklist_response.data["checklist_id"]

        first = self.client.post(
            self.mommy_selection_url,
            {"symptom_ids": [self.mommy_1.pk], "checklist_id": checklist_id},
            format="json",
        )
        second = self.client.post(
            self.mommy_selection_url,
            {"symptom_ids": [self.mommy_2.pk], "checklist_id": checklist_id},
            format="json",
        )

        self.assertEqual(first.status_code, 200, first.data)
        self.assertEqual(second.status_code, 200, second.data)
        events = list(SymptomChecklistResponse.objects.order_by("submitted_at"))
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0].reported_symptom_codes, ["mommy.api_headache"])
        self.assertEqual(events[1].reported_symptom_codes, ["mommy.api_dizziness"])
        self.assertEqual(
            list(
                UserMommySymptoms.objects.filter(user=self.user).values_list(
                    "symptom_id", flat=True
                )
            ),
            [self.mommy_2.pk],
        )
        checklist = GeneratedSymptomChecklist.objects.get(pk=checklist_id)
        current_statuses = {
            item.symptom_code: item.status for item in checklist.items.all()
        }
        self.assertEqual(
            current_statuses,
            {
                "mommy.api_headache": SYMPTOM_STATUS_NOT_REPORTED,
                "mommy.api_dizziness": SYMPTOM_STATUS_REPORTED,
            },
        )

    def test_foreign_or_wrong_type_checklist_is_rejected_without_legacy_write(self):
        foreign = GeneratedSymptomChecklist.objects.create(
            user=self.other_user,
            checklist_type=SYMPTOM_CHECKLIST_MOMMY,
            local_date=timezone.localdate(),
            algorithm_version="test",
        )
        wrong_type = GeneratedSymptomChecklist.objects.create(
            user=self.user,
            checklist_type=SYMPTOM_CHECKLIST_BABY,
            local_date=timezone.localdate(),
            algorithm_version="test",
        )

        for checklist_id in (foreign.pk, wrong_type.pk, uuid4()):
            response = self.client.post(
                self.mommy_selection_url,
                {
                    "symptom_ids": [self.mommy_1.pk],
                    "checklist_id": checklist_id,
                },
                format="json",
            )
            self.assertEqual(response.status_code, 400, response.data)

        self.assertEqual(UserMommySymptoms.objects.filter(user=self.user).count(), 0)
        self.assertEqual(SymptomChecklistResponse.objects.count(), 0)

    def test_baby_checklist_has_independent_type_and_stable_code(self):
        with patch(
            "recommendations.services.symptom_monitoring.generate_symptoms",
            return_value=[self.baby_1],
        ):
            response = self.client.get(self.baby_checklist_url)

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["symptoms"][0]["code"], "baby.api_reduced_movement")
        checklist = GeneratedSymptomChecklist.objects.get(pk=response.data["checklist_id"])
        self.assertEqual(checklist.checklist_type, SYMPTOM_CHECKLIST_BABY)

        selection = self.client.post(
            self.baby_selection_url,
            {"symptom_ids": [self.baby_1.pk]},
            format="json",
        )
        self.assertEqual(selection.status_code, 200, selection.data)
        self.assertEqual(
            str(selection.data["checklist_id"]),
            str(response.data["checklist_id"]),
        )
        event = SymptomChecklistResponse.objects.get(
            checklist_type=SYMPTOM_CHECKLIST_BABY
        )
        self.assertEqual(event.items.get().status, SYMPTOM_STATUS_REPORTED)
