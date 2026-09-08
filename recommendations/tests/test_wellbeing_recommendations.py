from datetime import datetime, timedelta, timezone as dt_timezone
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from api.models import UserWellbeingLog, Wellbeing
from recommendations.context import EvalContextBuilder
from recommendations.evaluator import evaluate_recommendations


User = get_user_model()
MENTAL_RULE_IDS = {
    "mental.wellbeing.distressed",
    "mental.wellbeing.nervous",
    "mental.wellbeing.poor_sleep",
}


class WellbeingRecommendationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="mental-wellbeing@example.com",
            password="testpass123",
            timezone="UTC",
        )
        self.distressed = Wellbeing.objects.get(code="distressed")
        self.nervous = Wellbeing.objects.get(code="nervous")
        self.poor_sleep = Wellbeing.objects.get(code="poor_sleep")

    def _mental_recommendations(self):
        return [
            item
            for item in evaluate_recommendations(self.user)
            if item.get("rule_id") in MENTAL_RULE_IDS
        ]

    def test_missing_wellbeing_is_an_empty_safe_context(self):
        context = EvalContextBuilder(self.user).build()

        self.assertEqual(
            context["wellbeing"],
            {"date": None, "moods": set(), "feelings": set()},
        )
        self.assertFalse(context["mood"]("distressed"))
        self.assertFalse(context["feeling"]("poor_sleep"))
        self.assertEqual(self._mental_recommendations(), [])

    def test_previous_day_wellbeing_is_ignored(self):
        log = UserWellbeingLog.objects.create(
            user=self.user,
            date=timezone.localdate() - timedelta(days=1),
        )
        log.moods.add(self.distressed)

        self.assertEqual(self._mental_recommendations(), [])

    def test_distressed_has_priority_over_other_wellbeing_signals(self):
        log = UserWellbeingLog.objects.create(
            user=self.user,
            date=timezone.localdate(),
        )
        log.moods.add(self.distressed, self.nervous)
        log.feelings.add(self.poor_sleep)

        recommendations = self._mental_recommendations()

        self.assertEqual(len(recommendations), 1)
        self.assertEqual(
            recommendations[0]["rule_id"], "mental.wellbeing.distressed"
        )
        self.assertTrue(recommendations[0]["recommendation_mental"])

    def test_nervous_and_poor_sleep_each_create_one_mental_recommendation(self):
        for item, relation, expected_rule_id in (
            (self.nervous, "moods", "mental.wellbeing.nervous"),
            (self.poor_sleep, "feelings", "mental.wellbeing.poor_sleep"),
        ):
            with self.subTest(expected_rule_id=expected_rule_id):
                UserWellbeingLog.objects.filter(user=self.user).delete()
                log = UserWellbeingLog.objects.create(
                    user=self.user,
                    date=timezone.localdate(),
                )
                getattr(log, relation).add(item)

                recommendations = self._mental_recommendations()

                self.assertEqual(
                    [recommendation["rule_id"] for recommendation in recommendations],
                    [expected_rule_id],
                )

    @patch("recommendations.context.timezone.now")
    def test_wellbeing_uses_the_users_local_date(self, now):
        now.return_value = datetime(2026, 9, 7, 23, 30, tzinfo=dt_timezone.utc)
        self.user.timezone = "Europe/Minsk"
        self.user.save(update_fields=["timezone"])
        log = UserWellbeingLog.objects.create(user=self.user, date="2026-09-08")
        log.moods.add(self.nervous)

        context = EvalContextBuilder(self.user).build()

        self.assertEqual(context["wellbeing"]["date"], "2026-09-08")
        self.assertTrue(context["mood"]("nervous"))
