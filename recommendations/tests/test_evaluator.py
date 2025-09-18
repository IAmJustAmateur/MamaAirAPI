# recommendations/tests/test_evaluator.py
from django.test import TestCase
from django.utils import timezone
from django.contrib.auth import get_user_model

from recommendations.evaluator import (
    evaluate_recommendations,
    generate_health_insight_snapshot,
)
from recommendations.models import RecommendationRule
from api.models import (
    UserLifeStyle,
    Exposure,
    MommySymptom,
    UserMommySymptoms,
    BabySymptom,
    UserBabySymptoms,
)

from .utils import make_user_with_bmi

User = get_user_model()


class EvaluatorTests(TestCase):
    def setUp(self):
        self.u = make_user_with_bmi(
            email="u1@example.com",
            bmi=31.0,  # хотим >=30
            height_cm=170,
            week_of_pregnancy=22,
        )
        UserLifeStyle.objects.create(
            user=self.u,
            average_sleep_hours=5.0,
            activity_duration_minutes=120,
            cooking_method="gas",
        )
        Exposure.objects.create(
            user=self.u,
            timestamp=timezone.localdate(),
            exposure_level=4.0,
            pollutants={"pm25_avg_24h": 10, "no2_24h_mean": 26},
        )

        # Небезопасное правило (проверка песочницы)
        RecommendationRule.objects.get_or_create(
            rule_id="bad.builtin",
            version=1,
            title="Bad",
            condition="open('/etc/passwd') or True",
            message="...",
            severity="info",
            category="general",
            enabled=True,
            priority=70,
            cooldown_hours=24,
            ttl_hours=24,
        )

    def test_safe_eval_and_matching(self):
        recs = evaluate_recommendations(self.u)
        ids = [r["id"] for r in recs]
        self.assertIn("alert.pm25.daily.v1", ids)
        self.assertIn("alert.sleep.low.v1", ids)
        # Правило с open(...) не должно свалить и не должно матчиться
        self.assertNotIn("bad.builtin.v1", ids)

    def test_snapshot_creation_and_ttl(self):
        snap = generate_health_insight_snapshot(self.u, trigger_event="login")
        self.assertGreaterEqual(len(snap.recommendations), 1)
        for item in snap.recommendations:
            self.assertIn("expires_at", item)
            self.assertIn("engine_version", item)
