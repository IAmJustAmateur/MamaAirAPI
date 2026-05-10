from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from api.models import DailyTask


class DailyTaskApiTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(
            email="daily-tasks@example.com",
            password="pass12345",
            name="Daily Tasks User",
        )
        DailyTask.objects.all().delete()
        DailyTask.objects.create(
            code="third_task",
            title="Third Task",
            sort_order=30,
        )
        DailyTask.objects.create(
            code="first_task",
            title="First Task",
            sort_order=10,
        )
        DailyTask.objects.create(
            code="inactive_task",
            title="Inactive Task",
            sort_order=20,
            is_active=False,
        )
        DailyTask.objects.create(
            code="second_task",
            title="Second Task",
            sort_order=20,
        )

    def setUp(self):
        self.url = reverse("daily-tasks")
        self.client.force_authenticate(self.user)

    def test_get_returns_active_daily_tasks_ordered(self):
        resp = self.client.get(self.url)

        assert resp.status_code == status.HTTP_200_OK
        assert resp.data == [
            {"code": "first_task", "title": "First Task", "sort_order": 10},
            {"code": "second_task", "title": "Second Task", "sort_order": 20},
            {"code": "third_task", "title": "Third Task", "sort_order": 30},
        ]

    def test_get_excludes_inactive_daily_tasks(self):
        resp = self.client.get(self.url)

        assert resp.status_code == status.HTTP_200_OK
        codes = [item["code"] for item in resp.data]
        assert "inactive_task" not in codes

    def test_endpoint_requires_auth(self):
        self.client.force_authenticate(user=None)

        resp = self.client.get(self.url)

        assert resp.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )
