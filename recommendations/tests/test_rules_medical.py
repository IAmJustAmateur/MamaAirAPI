# recommendations/tests/test_rules_medical.py
from datetime import timedelta
from django.test import TestCase
from django.utils import timezone
from django.contrib.auth import get_user_model

from recommendations.evaluator import evaluate_recommendations

from api.models import (
    MommySymptom,
    BabySymptom,
    UserMommySymptoms,
    UserBabySymptoms,
    UserLifeStyle,
    Exposure,
)

User = get_user_model()


class MedicalRulesTests(TestCase):
    def setUp(self):
        self.u = User.objects.create_user(
            email="u@test.com",
            password="x",
            week_of_pregnancy=22,
            height=170,
            weight_pre_pregnancy=70.0,
        )
        self.u.set_pregnancy_start_date()
        UserLifeStyle.objects.create(user=self.u)
        Exposure.objects.create(
            user=self.u,
            timestamp=timezone.localdate(),
            exposure_level=3.0,
            pollutants={},
        )
        # симптомы за последние 6 часов
        t = timezone.now() - timedelta(hours=6)
        self.hbp, _ = MommySymptom.objects.get_or_create(name="high blood pressure")
        self.hd, _ = MommySymptom.objects.get_or_create(name="headache")
        self.uap, _ = MommySymptom.objects.get_or_create(name="upper abdominal pain")
        self.rm, _ = BabySymptom.objects.get_or_create(name="reduced fetal movement")

        # Зарегистрируем 3 из 4 для преэклампсии
        UserMommySymptoms.objects.create(user=self.u, symptom=self.hbp, recorded_at=t)
        UserMommySymptoms.objects.create(user=self.u, symptom=self.hd, recorded_at=t)
        UserMommySymptoms.objects.create(user=self.u, symptom=self.uap, recorded_at=t)

        # Правило преэклампсии
        # RecommendationRule.objects.create(
        #     rule_id="alert.preeclampsia",
        #     version=1,
        #     title="PE",
        #     condition="count_true(is_20w_plus, m('high blood pressure'), m('headache'), m('upper abdominal pain'), b('reduced fetal movement')) >= 3",
        #     message="...",
        #     severity="critical",
        #     category="medical",
        #     enabled=True,
        #     priority=6,
        #     cooldown_hours=24,
        #     ttl_hours=24,
        # )

    def test_preeclampsia_triggers(self):
        recs = evaluate_recommendations(self.u)
        ids = [r["id"] for r in recs]
        self.assertIn("alert.preeclampsia.v1", ids)

    def test_anemia_triggers(self):
        t = timezone.now() - timedelta(hours=2)
        fatigue, _ = MommySymptom.objects.get_or_create(name="persistent fatigue")
        dizziness, _ = MommySymptom.objects.get_or_create(name="dizziness")
        UserMommySymptoms.objects.create(user=self.u, symptom=fatigue, recorded_at=t)
        UserMommySymptoms.objects.create(user=self.u, symptom=dizziness, recorded_at=t)

        recs = evaluate_recommendations(self.u)
        ids = [r["id"] for r in recs]
        self.assertIn("alert.anemia.v1", ids)

    def test_prom_triggers(self):
        t = timezone.now() - timedelta(hours=2)
        leaking, _ = MommySymptom.objects.get_or_create(name="leaking fluid")
        UserMommySymptoms.objects.create(user=self.u, symptom=leaking, recorded_at=t)

        recs = evaluate_recommendations(self.u)
        ids = [r["id"] for r in recs]
        self.assertIn("alert.prom.v1", ids)

    def test_fetal_hypoxia_triggers(self):
        t = timezone.now() - timedelta(hours=2)
        stillness, _ = BabySymptom.objects.get_or_create(name="prolonged stillness")
        UserBabySymptoms.objects.create(user=self.u, symptom=stillness, recorded_at=t)

        recs = evaluate_recommendations(self.u)
        ids = [r["id"] for r in recs]
        self.assertIn("alert.fetal_hypoxia.v1", ids)

    def test_cardiovascular_triggers(self):
        t = timezone.now() - timedelta(hours=2)
        chest_pain, _ = MommySymptom.objects.get_or_create(name="chest pain")
        UserMommySymptoms.objects.create(
            user=self.u, symptom=chest_pain, recorded_at=t
        )

        recs = evaluate_recommendations(self.u)
        ids = [r["id"] for r in recs]
        self.assertIn("alert.cardiovascular.v1", ids)
