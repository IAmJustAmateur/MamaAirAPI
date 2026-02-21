from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from django.contrib.auth import get_user_model
from api.models import (
    HealthInsightSnapshot,
    RecommendationCompletion,
)

User = get_user_model()


class RecommendationCompletionApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="u1@example.com", password="pass1234", is_active=True
        )
        self.user2 = User.objects.create_user(
            email="u2@example.com", password="pass1234", is_active=True
        )
        self.client.force_authenticate(self.user)

        self.snapshot = HealthInsightSnapshot.objects.create(
            user=self.user, recommendations=[{"id": "x"}]
        )
        self.snapshot2 = HealthInsightSnapshot.objects.create(
            user=self.user2, recommendations=[{"id": "y"}]
        )

        self.url = reverse("recommendation-completion")

    def test_post_creates_completion(self):
        payload = {
            "snapshot_id": self.snapshot.id,
            "rule_id": "alert.pm25.daily",
            "rule_version": 1,
            "dimension": "activity",
            "status": "done",
        }
        resp = self.client.post(self.url, payload, format="json")
        self.assertIn(resp.status_code, (status.HTTP_201_CREATED, status.HTTP_200_OK))
        self.assertEqual(resp.data["snapshot_id"], self.snapshot.id)
        self.assertEqual(resp.data["status"], "done")

        self.assertEqual(
            RecommendationCompletion.objects.filter(user=self.user).count(), 1
        )

    def test_post_updates_existing_completion(self):
        RecommendationCompletion.objects.create(
            user=self.user,
            snapshot=self.snapshot,
            rule_id="alert.pm25.daily",
            rule_version=1,
            dimension="activity",
            status="done",
        )

        payload = {
            "snapshot_id": self.snapshot.id,
            "rule_id": "alert.pm25.daily",
            "rule_version": 1,
            "dimension": "activity",
            "status": "skipped",
        }
        resp = self.client.post(self.url, payload, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["status"], "skipped")

        obj = RecommendationCompletion.objects.get(
            user=self.user,
            snapshot=self.snapshot,
            rule_id="alert.pm25.daily",
            rule_version=1,
            dimension="activity",
        )
        self.assertEqual(obj.status, "skipped")

    def test_get_lists_only_user_items(self):
        RecommendationCompletion.objects.create(
            user=self.user,
            snapshot=self.snapshot,
            rule_id="r1",
            rule_version=1,
            dimension="diet",
            status="done",
        )
        RecommendationCompletion.objects.create(
            user=self.user2,
            snapshot=self.snapshot2,
            rule_id="r2",
            rule_version=1,
            dimension="diet",
            status="done",
        )

        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data), 1)
        self.assertEqual(resp.data[0]["rule_id"], "r1")

    def test_cannot_post_for_other_users_snapshot(self):
        payload = {
            "snapshot_id": self.snapshot2.id,  # чужой
            "rule_id": "alert.pm25.daily",
            "rule_version": 1,
            "dimension": "activity",
            "status": "done",
        }
        resp = self.client.post(self.url, payload, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
