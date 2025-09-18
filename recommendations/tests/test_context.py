# recommendations/tests/test_context.py
from datetime import timedelta
from django.test import TestCase
from django.utils import timezone

from django.contrib.auth import get_user_model
from recommendations.context import EvalContextBuilder
from api.models import (
    MommySymptom,
    BabySymptom,
    UserMommySymptoms,
    UserBabySymptoms,
    Exposure,
    UserLifeStyle,
)
from .utils import make_user_with_bmi

User = get_user_model()


class EvalContextBuilderTests(TestCase):
    def setUp(self):
        self.u = make_user_with_bmi(
            email="u@test.com",
            bmi=31.0,  # хотим >=30
            height_cm=170,
            week_of_pregnancy=22,
        )
        # Lifestyle OneToOne
        self.ls = UserLifeStyle.objects.create(
            user=self.u,
            average_sleep_hours=5.5,
            work_type="Desk",
            diet_type="carnivore",
            cooking_method="gas",
            activity_duration_minutes=120,
        )
        # Exposure (берём последний)
        Exposure.objects.create(
            user=self.u,
            timestamp=timezone.localdate() - timedelta(days=1),
            exposure_level=3.0,
            pollutants={"pm25_avg": 8},
        )
        Exposure.objects.create(
            user=self.u,
            timestamp=timezone.localdate(),
            exposure_level=4.0,
            pollutants={"pm25_avg": 10, "no2_24h_mean": 26},
        )

        # Symptoms (в окне и вне окна)
        h24 = timezone.now() - timedelta(hours=6)
        h30 = timezone.now() - timedelta(hours=30)

        mom_headache, _ = MommySymptom.objects.get_or_create(name="headache")
        mom_upper_typo, _ = MommySymptom.objects.get_or_create(
            name="upper updominal pain"
        )  # проверим алиас
        mom_old, _ = MommySymptom.objects.get_or_create(name="lower back pain")

        UserMommySymptoms.objects.create(
            user=self.u, symptom=mom_headache, recorded_at=h24
        )
        UserMommySymptoms.objects.create(
            user=self.u, symptom=mom_upper_typo, recorded_at=h24
        )
        UserMommySymptoms.objects.create(
            user=self.u, symptom=mom_old, recorded_at=h30
        )  # вне окна 24ч

        baby_rm, _ = BabySymptom.objects.get_or_create(name="reduced fetal movement")
        UserBabySymptoms.objects.create(user=self.u, symptom=baby_rm, recorded_at=h24)

    def test_build_profile_lifestyle_aq(self):
        ctx = EvalContextBuilder(self.u, recent_hours=24).build()
        self.assertEqual(round(ctx["profile"]["bmi"], 0), 31)
        self.assertTrue(ctx["is_20w_plus"])
        self.assertEqual(ctx["lifestyle"]["cooking_method"], "gas")
        self.assertEqual(ctx["aq"]["pollutants"]["pm25_avg"], 10)
        self.assertEqual(ctx["aq"]["pollutants"]["no2_24h_mean"], 26)

    def test_symptoms_window_and_aliases(self):
        ctx = EvalContextBuilder(self.u, recent_hours=24).build()
        # из алиаса "upper updominal pain" -> "upper abdominal pain"
        self.assertTrue(ctx["sym_m"].get("upper abdominal pain"))
        # старый симптом вне окна не попадает
        self.assertFalse(ctx["sym_m"].get("lower back pain", False))
        # baby-симптом
        self.assertTrue(ctx["sym_b"].get("reduced fetal movement"))
        # хелперы
        self.assertTrue(ctx["m"]("headache"))
        self.assertTrue(ctx["m"]("upper abdominal pain"))
        self.assertTrue(ctx["b"]("reduced fetal movement"))
        self.assertEqual(
            ctx["count_m"]("headache", "upper abdominal pain", "lower back pain"), 2
        )
