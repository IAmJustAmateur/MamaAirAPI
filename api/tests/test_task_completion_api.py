from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
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

    def test_get_without_params_returns_current_week(self):
        today = timezone.localdate()
        week_start = today - timedelta(days=today.weekday())
        UserDailyTaskCompletion.objects.create(
            user=self.user,
            date=today,
            task=self.drink_water,
            completed=True,
        )
        if week_start != today:
            UserDailyTaskCompletion.objects.create(
                user=self.user,
                date=week_start,
                task=self.cooking_smoke,
                completed=True,
            )
        UserDailyTaskCompletion.objects.create(
            user=self.other_user,
            date=today,
            task=self.morning_walk,
            completed=True,
        )

        resp = self.client.get(self.url)

        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["start_date"] == week_start.isoformat()
        assert resp.data["end_date"] == today.isoformat()
        assert resp.data["days_requested"] == (today - week_start).days + 1
        dates = [item["date"] for item in resp.data["items"]]
        assert today.isoformat() in dates
        assert dates == sorted(dates)

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

    def test_get_period_returns_completed_tasks_in_range(self):
        today = timezone.localdate()
        start = today - timedelta(days=6)
        in_range_old = today - timedelta(days=4)
        in_range_new = today - timedelta(days=1)
        outside = today - timedelta(days=8)
        UserDailyTaskCompletion.objects.create(
            user=self.user,
            date=outside,
            task=self.drink_water,
            completed=True,
        )
        UserDailyTaskCompletion.objects.create(
            user=self.user,
            date=in_range_old,
            task=self.cooking_smoke,
            completed=True,
        )
        UserDailyTaskCompletion.objects.create(
            user=self.user,
            date=in_range_new,
            task=self.drink_water,
            completed=True,
        )
        UserDailyTaskCompletion.objects.create(
            user=self.user,
            date=in_range_new,
            task=self.morning_walk,
            completed=False,
        )
        UserDailyTaskCompletion.objects.create(
            user=self.other_user,
            date=in_range_new,
            task=self.morning_walk,
            completed=True,
        )

        resp = self.client.get(
            self.url,
            {
                "start_date": start.isoformat(),
                "end_date": today.isoformat(),
            },
        )

        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["start_date"] == start.isoformat()
        assert resp.data["end_date"] == today.isoformat()
        assert resp.data["days_requested"] == 7
        assert resp.data["items"] == [
            {"date": in_range_old.isoformat(), "tasks": ["cooking_smoke"]},
            {"date": in_range_new.isoformat(), "tasks": ["drink_water"]},
        ]

    def test_get_rejects_mixed_single_day_and_period_params(self):
        today = timezone.localdate().isoformat()
        resp = self.client.get(
            self.url,
            {
                "date": today,
                "start_date": today,
                "end_date": today,
            },
        )

        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert "cannot be combined" in resp.data["detail"]

    def test_get_period_requires_start_and_end_together(self):
        resp = self.client.get(self.url, {"start_date": timezone.localdate().isoformat()})

        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert "together" in resp.data["detail"]

    def test_get_rejects_invalid_dates(self):
        today = timezone.localdate()

        resp = self.client.get(self.url, {"date": "not-a-date"})
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert "date" in resp.data["detail"]

        resp = self.client.get(self.url, {"date": (today + timedelta(days=1)).isoformat()})
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert "later than today" in resp.data["detail"]

        resp = self.client.get(
            self.url,
            {
                "start_date": today.isoformat(),
                "end_date": (today + timedelta(days=1)).isoformat(),
            },
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert "later than today" in resp.data["detail"]

        resp = self.client.get(
            self.url,
            {
                "start_date": today.isoformat(),
                "end_date": (today - timedelta(days=1)).isoformat(),
            },
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert "start_date" in resp.data["detail"]

    def test_get_period_rejects_more_than_90_days(self):
        today = timezone.localdate()

        resp = self.client.get(
            self.url,
            {
                "start_date": (today - timedelta(days=100)).isoformat(),
                "end_date": today.isoformat(),
            },
        )

        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert "90 days" in resp.data["detail"]

    def test_endpoint_requires_auth(self):
        self.client.force_authenticate(user=None)

        resp = self.client.get(self.url, {"date": "2026-04-30"})

        assert resp.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )
