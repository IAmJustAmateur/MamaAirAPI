from datetime import date

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from api.models import DailyTask, UserDailyTaskCompletion


class TaskCompletionApiTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(
            email="task-completion@example.com",
            password="pass12345",
            name="Task Completion User",
        )
        cls.other_user = User.objects.create_user(
            email="task-completion-other@example.com",
            password="pass12345",
            name="Other User",
        )
        cls.drink_water, _ = DailyTask.objects.get_or_create(
            code="drink_water",
            defaults={"title": "Drink water", "sort_order": 10},
        )
        cls.cooking_smoke, _ = DailyTask.objects.get_or_create(
            code="cooking_smoke",
            defaults={"title": "Cooking Smoke", "sort_order": 20},
        )
        cls.morning_walk, _ = DailyTask.objects.get_or_create(
            code="morning_walk",
            defaults={"title": "Morning Walk", "sort_order": 30},
        )

    def setUp(self):
        self.client.force_authenticate(self.user)
        self.url = reverse("task-completion")

    def test_post_creates_task_completions_for_date(self):
        payload = {
            "date": "2026-04-30",
            "tasks": ["cooking_smoke", "drink_water"],
        }

        resp = self.client.post(self.url, payload, format="json")

        assert resp.status_code == status.HTTP_201_CREATED
        assert resp.data == {
            "date": "2026-04-30",
            "tasks": ["cooking_smoke", "drink_water"],
        }
        assert UserDailyTaskCompletion.objects.filter(
            user=self.user,
            date=date(2026, 4, 30),
            completed=True,
        ).count() == 2

    def test_post_replaces_task_completions_for_date(self):
        UserDailyTaskCompletion.objects.create(
            user=self.user,
            date=date(2026, 4, 30),
            task=self.morning_walk,
            completed=True,
        )

        resp = self.client.post(
            self.url,
            {"date": "2026-04-30", "tasks": ["drink_water"]},
            format="json",
        )

        assert resp.status_code == status.HTTP_201_CREATED
        assert resp.data == {"date": "2026-04-30", "tasks": ["drink_water"]}
        assert UserDailyTaskCompletion.objects.get(
            user=self.user,
            date=date(2026, 4, 30),
            task=self.morning_walk,
        ).completed is False
        assert UserDailyTaskCompletion.objects.get(
            user=self.user,
            date=date(2026, 4, 30),
            task=self.drink_water,
        ).completed is True

    def test_post_rejects_unknown_task_code(self):
        resp = self.client.post(
            self.url,
            {"date": "2026-04-30", "tasks": ["unknown_task"]},
            format="json",
        )

        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert "tasks" in resp.data

    def test_get_requires_date_param(self):
        resp = self.client.get(self.url)

        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert "date" in resp.data.get("detail", "").lower()

    def test_get_returns_completed_tasks_for_date(self):
        UserDailyTaskCompletion.objects.create(
            user=self.user,
            date=date(2026, 4, 30),
            task=self.drink_water,
            completed=True,
        )
        UserDailyTaskCompletion.objects.create(
            user=self.user,
            date=date(2026, 4, 30),
            task=self.morning_walk,
            completed=False,
        )
        UserDailyTaskCompletion.objects.create(
            user=self.other_user,
            date=date(2026, 4, 30),
            task=self.cooking_smoke,
            completed=True,
        )

        resp = self.client.get(self.url, {"date": "2026-04-30"})

        assert resp.status_code == status.HTTP_200_OK
        assert resp.data == {"date": "2026-04-30", "tasks": ["drink_water"]}

    def test_endpoint_requires_auth(self):
        self.client.force_authenticate(user=None)

        resp = self.client.get(self.url, {"date": "2026-04-30"})

        assert resp.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )
