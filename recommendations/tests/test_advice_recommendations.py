# tests/test_advice_recommendations.py
from unittest.mock import patch

from django.urls import reverse
from django.utils import timezone
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from api.models import UserLifeStyle
from api.models import (
    MommySymptom,
    UserMommySymptoms,
    BabySymptom,
    UserBabySymptoms,
)

from api.models import (
    HealthInsightSnapshot,
    AirExposureLog,
    Exposure,
)
from .utils import _build_movements_csv_many

User = get_user_model()


class AdviceEndpointTests(APITestCase):
    """
    Локальные интеграционные тесты для /api/advice/
    Покрывают категории: medical, air_quality, lifestyle, general.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email="advtest@example.com", password="pass12345"
        )
        self.client.force_authenticate(self.user)
        self.url = reverse("advice")

    # ---------- helpers -------------------------------------------------------

    def _wipe_snapshots(self):
        HealthInsightSnapshot.objects.filter(user=self.user).delete()

    def _set_profile(self, **kwargs):
        """
        Обновляет профиль пользователя. Минимально используем:
        - height (см), weight_pre_pregnancy (кг), week_of_pregnancy (целое)
        Остальные поля игнорируются.
        """
        for k, v in kwargs.items():
            setattr(self.user, k, v)
        if "week_of_pregnancy" in kwargs:
            self.user.set_pregnancy_start_date()  # чтобы week_of_pregnancy работала корректно
        self.user.save()

    def _ensure_lifestyle(self, **kwargs) -> UserLifeStyle:
        ls, _ = UserLifeStyle.objects.get_or_create(user=self.user)
        for k, v in kwargs.items():
            setattr(ls, k, v)
        ls.save()
        return ls

    def _add_mommy_symptoms_now(self, *names):
        """
        Создаёт (если нужно) справочные MommySymptom с указанными именами
        и добавляет факты пользователя на текущее время (aware datetime).
        """
        now = timezone.now()
        for name in names:
            sym, _ = MommySymptom.objects.get_or_create(name=name)
            UserMommySymptoms.objects.create(
                user=self.user, symptom=sym, recorded_at=now
            )

    def _add_baby_symptoms_now(self, *names):
        now = timezone.now()
        for name in names:
            sym, _ = BabySymptom.objects.get_or_create(name=name)
            UserBabySymptoms.objects.create(
                user=self.user, symptom=sym, recorded_at=now
            )

    def _upload_movements_many(self):
        """
        POST /api/movements/upload/ локально.
        Возвращает Response.
        """
        file = _build_movements_csv_many()
        url = reverse("movements-upload")  # имя эндпойнта из твоих тестов
        resp = self.client.post(url, {"file": file}, format="multipart")
        self.assertIn(
            resp.status_code,
            (201, 207),
            resp.data if hasattr(resp, "data") else resp.content[:300],
        )
        return resp

    def _get_recommendations(self):
        """
        Дёргаем /api/advice/ и возвращаем список карточек snapshot['recommendations'].
        По твоему коду HealthInsightView всегда возвращает 200 с сериализованным свежим снапшотом.
        """
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200, resp.data)
        data = resp.json()
        self.assertIn("recommendations", data, data)
        recs = data["recommendations"]
        self.assertIsInstance(recs, list)
        return recs

    def _has_rule(self, recs, rule_id: str) -> bool:
        return any(isinstance(r, dict) and r.get("rule_id") == rule_id for r in recs)

    def _has_category(self, recs, category: str) -> bool:
        return any(isinstance(r, dict) and r.get("category") == category for r in recs)

    # ---------- tests ---------------------------------------------------------

    def test_medical_placental_abruption(self):
        """
        Должно сработать правило alert.placental_abruption:
        count_true(m('vaginal bleeding'), m('abdominal pain'), m('lower back pain'),
                   m('contractions'), m('uterine tenderness'), m('uterine rigidity')) >= 3
        """
        self._wipe_snapshots()
        # Профиль здесь не критичен
        self._set_profile(height=170, weight_pre_pregnancy=65, week_of_pregnancy=18)

        # Добавим 3 мамских симптома
        self._add_mommy_symptoms_now(
            "vaginal bleeding",
            "abdominal pain",
            "contractions",
        )

        recs = self._get_recommendations()
        self.assertTrue(self._has_rule(recs, "alert.placental_abruption"), recs)
        self.assertTrue(self._has_category(recs, "medical"), recs)

    def test_medical_preeclampsia(self):
        """
        Должно сработать правило alert.preeclampsia при week>=20 и 3 мамских симптомах.
        """
        self._wipe_snapshots()
        self._set_profile(height=170, weight_pre_pregnancy=65, week_of_pregnancy=22)

        self._add_mommy_symptoms_now(
            "high blood pressure",
            "headache",
            "upper abdominal pain",
        )
        # b('reduced fetal movement') не обязателен, т.к. уже 3 мамских

        recs = self._get_recommendations()
        self.assertTrue(self._has_rule(recs, "alert.preeclampsia"), recs)
        self.assertTrue(self._has_category(recs, "medical"), recs)

    @patch("api.services.air_exposure_daily.recompute_daily_exposure")
    def test_air_quality_pm25_high(self, mock_recompute):
        """
        Правило alert.pm25.daily при ge_poll('pm25_24h_mean', 10).
        Загрузим перемещения и гарантируем агрегаты через мок пересчёта.
        """
        self._wipe_snapshots()
        self._set_profile(height=170, weight_pre_pregnancy=65, week_of_pregnancy=20)

        # 1) загрузка перемещений
        self._upload_movements_many()

        # 2) имитируем пересчёт дневной экспозиции так, чтобы появились нужные метрики
        #    pm25_24h_mean >= 10 (например 15).
        def _fake_recompute(user):
            from api.models import Exposure

            es = Exposure.objects.filter(user=user)
            for e in es:
                e.pollutants = e.pollutants or {}
                e.pollutants["pm25_avg_24h"] = 15.0
                e.save()
            return True

        mock_recompute.side_effect = _fake_recompute

        # 3) триггерим пересчёт (если он не выполняется автоматически в загрузчике)
        # Если твой upload сам вызывает recompute_daily_exposure — этот вызов можно опустить.
        _ = mock_recompute(self.user)

        recs = self._get_recommendations()
        self.assertTrue(self._has_rule(recs, "alert.pm25.daily"), recs)
        self.assertTrue(self._has_category(recs, "air_quality"), recs)
        match = next((r for r in recs if r.get("rule_id") == "alert.pm25.daily"), {})
        self.assertIn("smoke exposure", match.get("alert", "").lower())

    def test_lifestyle_sleep_low(self):
        """
        Должно сработать правило alert.sleep.low при average_sleep_hours < 6
        (или avg_sleep_7d < 7).
        """
        self._wipe_snapshots()
        self._set_profile(height=170, weight_pre_pregnancy=65, week_of_pregnancy=18)
        self._ensure_lifestyle(average_sleep_hours=5.5)

        recs = self._get_recommendations()
        self.assertTrue(self._has_rule(recs, "alert.sleep.low"), recs)
        self.assertTrue(self._has_category(recs, "lifestyle"), recs)

    def test_general_bmi_high(self):
        """
        Должно сработать правило alert.bmi.high при bmi >= 30.
        bmi = weight_pre_pregnancy / (height/100)^2
        Пример: рост 160 см, вес 90 кг -> BMI ~ 35.2
        """
        self._wipe_snapshots()
        self._set_profile(height=160, weight_pre_pregnancy=90, week_of_pregnancy=18)

        recs = self._get_recommendations()
        self.assertTrue(self._has_rule(recs, "alert.bmi.high"), recs)
        self.assertTrue(self._has_category(recs, "general"), recs)

    def test_medical_hyperemesis_level3(self):
        self._wipe_snapshots()
        self._set_profile(height=170, weight_pre_pregnancy=65, week_of_pregnancy=12)
        self._add_mommy_symptoms_now("severe vomiting")

        recs = self._get_recommendations()
        match = next(
            (r for r in recs if r.get("rule_id") == "alert.hyperemesis"), None
        )
        self.assertIsNotNone(match, recs)
        self.assertEqual(match["category"], "medical")
        self.assertIn("severe vomiting", match["alert"].lower())
        self.assertIn("ogi", match["recommendation_diet"].lower())
        self.assertIn("cool", match["recommendation_activity"].lower())
        self.assertIn("fluids", match["recommendation_behavior"].lower())

    def test_heat_and_indoor_solid_fuel_level3(self):
        self._wipe_snapshots()
        self._set_profile(height=170, weight_pre_pregnancy=65, week_of_pregnancy=18)
        self._ensure_lifestyle(
            cooking_method="charcoal",
            cooking_venue="indoor",
            ventilation_level="low",
            time_spent="mostly_outdoors",
            time_of_day="midday_or_afternoon",
        )
        AirExposureLog.objects.create(
            user=self.user,
            timestamp=timezone.now(),
            latitude=6.5244,
            longitude=3.3792,
            temperature=36.5,
            humidity=70,
            exposure_minutes=60,
        )

        recs = self._get_recommendations()
        self.assertTrue(self._has_rule(recs, "alert.heat.high"), recs)
        self.assertTrue(self._has_rule(recs, "alert.cooking.solid_fuel"), recs)
        self.assertTrue(self._has_rule(recs, "alert.cooking.indoor_solid_fuel"), recs)
        self.assertTrue(self._has_rule(recs, "alert.outdoor.midday"), recs)

    def test_gas_cooking_with_high_no2_level3(self):
        self._wipe_snapshots()
        self._set_profile(height=170, weight_pre_pregnancy=65, week_of_pregnancy=18)
        self._ensure_lifestyle(cooking_method="gas")
        Exposure.objects.create(
            user=self.user,
            timestamp=timezone.localdate(),
            exposure_level=2.0,
            pollutants={"no2_24h_mean": 26.0},
        )

        recs = self._get_recommendations()
        match = next(
            (r for r in recs if r.get("rule_id") == "alert.cooking.gas_and_no2_high"),
            None,
        )
        self.assertIsNotNone(match, recs)
        self.assertIn("gas cooking", match["alert"].lower())
        self.assertIn("electric", match["recommendation_behavior"].lower())

    def test_medical_gdm_level3(self):
        self._wipe_snapshots()
        self._set_profile(height=170, weight_pre_pregnancy=65, week_of_pregnancy=24)
        self._add_mommy_symptoms_now(
            "increased thirst",
            "increased urination",
            "dried mouth",
        )

        recs = self._get_recommendations()
        match = next((r for r in recs if r.get("rule_id") == "alert.gdm"), None)
        self.assertIsNotNone(match, recs)
        self.assertIn("glucose test", match["alert"].lower())
        self.assertIn("sorghum", match["recommendation_diet"].lower())
        self.assertIn("bitterleaf", match["recommendation_behavior"].lower())

    def test_medical_lbw_level3(self):
        self._wipe_snapshots()
        self._set_profile(height=170, weight_pre_pregnancy=65, week_of_pregnancy=28)
        self._add_mommy_symptoms_now("no belly growth", "poor appetite")
        self._add_baby_symptoms_now("reduced fetal movement")

        recs = self._get_recommendations()
        match = next((r for r in recs if r.get("rule_id") == "alert.lbw"), None)
        self.assertIsNotNone(match, recs)
        self.assertIn("fetal growth", match["alert"].lower())
        self.assertIn("koko plus", match["recommendation_diet"].lower())
        self.assertIn("heavy lifting", match["recommendation_activity"].lower())

    def test_medical_preterm_labor_level3(self):
        self._wipe_snapshots()
        self._set_profile(height=170, weight_pre_pregnancy=65, week_of_pregnancy=26)
        self._add_mommy_symptoms_now(
            "contraction frequency",
            "increased heart rate",
            "fever",
        )

        recs = self._get_recommendations()
        match = next(
            (r for r in recs if r.get("rule_id") == "alert.preterm_labor"), None
        )
        self.assertIsNotNone(match, recs)
        self.assertIn("preterm labor", match["alert"].lower())
        self.assertIn("heat", match["recommendation_diet"].lower())
        self.assertIn("neem", match["recommendation_behavior"].lower())
