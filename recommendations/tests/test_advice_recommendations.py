# tests/test_advice_recommendations.py
from datetime import datetime, timedelta, timezone as dt_tz
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
from api.models import AirExposureLog
from api.models import (
    HealthInsightSnapshot,
)

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

    def _create_air_exposure_log(self, **metrics) -> AirExposureLog:
        """
        Создаёт последний (по времени) AirExposureLog для пользователя.
        В metrics передаём нужные агрегаты, например:
         pm25_24h_mean=15, no2_24h_mean=30, o3_8h_max=120, so2_24h_mean=50
        """
        log = AirExposureLog.objects.create(
            user=self.user,
            timestamp=timezone.now(),  # последний лог
            **metrics,
        )
        return log

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

    def test_air_quality_pm25_high(self):
        """
        Должно сработать правило alert.pm25.daily при ge_poll('pm25_24h_mean', 10).
        """
        self._wipe_snapshots()
        self._set_profile(height=170, weight_pre_pregnancy=65, week_of_pregnancy=20)

        # создаём свежий лог экспозиции
        self._create_air_exposure_log(pm25_24h_mean=15)

        recs = self._get_recommendations()
        self.assertTrue(self._has_rule(recs, "alert.pm25.daily"), recs)
        self.assertTrue(self._has_category(recs, "air_quality"), recs)

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
