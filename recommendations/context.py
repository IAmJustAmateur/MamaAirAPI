# recommendations/context.py
from __future__ import annotations
from datetime import timedelta, timezone as dt_timezone
from typing import Dict, Set, Any, Iterable

from django.utils import timezone
from django.db.models import QuerySet

# Подстройте импорты под ваш app label (я использую "api")
from api.models import (
    User,
    MommySymptom,
    BabySymptom,
    UserMommySymptoms,
    UserBabySymptoms,
    Exposure,
    AirExposureLog,
    UserLifeStyle,  # модель с RISK_FIELDS
)


class EvalContextBuilder:
    """
    Собирает контекст для правил:
      - profile: bmi, full_year, race, week_of_pregnancy, is_20w_plus
      - lifestyle: поля из UserLifeStyle.RISK_FIELDS (последняя запись)
      - aq: pollutants из последнего Exposure + exposure_level
      - sym_m, sym_b: словари {симптом: True} за последние N часов
      - helpers: функции для удобных проверок в condition
    """

    # Простейшие алиасы/нормализация названий (можно расширять при необходимости)
    ALIASES = {
        "upper updominal pain": "upper abdominal pain",
        "updominal pain": "abdominal pain",
        "increase heart rate": "increased heart rate",
        "kick count low": "lower kick count",
        "stillness 6hr": "stillness 6h",
        "dried mouth": "dry mouth",
        "tiredness": "persistent tiredness",
        "contractions_gt_1_per_10min": "contraction frequency",
        "contractions": "contraction frequency",
        "abdominal or back pain": "non-specific abdominal pain",
        # добавляйте по мере необходимости
    }

    LIFESTYLE_CONTEXT_FIELDS = (
        "average_sleep_hours",
        "work_type",
        "diet_type",
        "cooking_method",
        "activity_duration_minutes",
        "work_schedule_pattern",
        "standing_hours_per_day",
        "area",
        "time_spent",
        "time_of_day",
        "commute_mode",
        "hydration_target_ml_per_day",
        "sleep_target_window",
        "rest_microbreak_preference",
        "supplement_preferences",
        "cooking_venue",
        "ventilation_level",
    )

    def __init__(self, user: User, recent_hours: int = 24) -> None:
        self.user = user
        self.recent_hours = recent_hours
        self._mommy_set: Set[str] = set()
        self._baby_set: Set[str] = set()
        self._aq: Dict[str, Any] = {}
        self._profile: Dict[str, Any] = {}
        self._lifestyle: Dict[str, Any] = {}

    # ---------- публичный метод ----------

    def build(self) -> Dict[str, Any]:
        self._profile = self._build_profile()
        self._lifestyle = self._build_lifestyle()
        self._aq = self._build_aq()
        sym_m = self._build_symptom_map(UserMommySymptoms)
        sym_b = self._build_symptom_map(UserBabySymptoms)

        # сохраняем множества для быстрых helper-функций
        self._mommy_set = set(k for k, v in sym_m.items() if v)
        self._baby_set = set(k for k, v in sym_b.items() if v)

        # helpers
        def _exists(v):
            return v is not None

        def _ge(a, b):
            return a is not None and b is not None and a >= b

        def _le(a, b):
            return a is not None and b is not None and a <= b

        def _count_true(*flags):
            return sum(bool(x) for x in flags)

        def _any_of(*flags):
            return any(bool(x) for x in flags)

        def _all_of(*flags):
            return all(bool(x) for x in flags)

        # работа с симптомами через функции (названия можно писать как в БД)
        def _norm(name: str) -> str:
            n = " ".join((name or "").strip().lower().split())
            return self.ALIASES.get(n, n)

        def m(name: str) -> bool:
            return _norm(name) in self._mommy_set

        def b(name: str) -> bool:
            return _norm(name) in self._baby_set

        def count_m(*names: str) -> int:
            return sum(1 for nm in names if m(nm))

        def count_b(*names: str) -> int:
            return sum(1 for nb in names if b(nb))

        # Поллютанты из Exposure
        def poll(key: str, default=None):
            return self._aq.get("pollutants", {}).get(key, default)

        def ge_poll(key: str, threshold: float) -> bool:
            val = poll(key)
            return (val is not None) and (val >= threshold)

        ctx = {
            # данные
            "profile": self._profile,
            "lifestyle": self._lifestyle,
            "aq": self._aq,  # {"pollutants": {...}, "exposure_level": x, "date": "YYYY-MM-DD"}
            "sym_m": sym_m,  # {"headache": True, "upper abdominal pain": True, ...}
            "sym_b": sym_b,  # {"reduced fetal movement": True, ...}
            # сокращённые булевы из профиля
            "is_20w_plus": bool(
                (self._profile.get("current_week_of_pregnancy") or 0) >= 20
            ),
            # helpers для условий
            "exists": _exists,
            "ge": _ge,
            "le": _le,
            "count_true": _count_true,
            "any_of": _any_of,
            "all_of": _all_of,
            "m": m,
            "b": b,
            "count_m": count_m,
            "count_b": count_b,
            "poll": poll,
            "ge_poll": ge_poll,
            "now": timezone.now,  # функция
        }
        return ctx

    # ---------- приватные сборщики ----------

    def _build_profile(self) -> Dict[str, Any]:
        u = self.user
        profile = {
            "bmi": getattr(u, "bmi", None),
            "full_year": getattr(u, "full_year", None),
            "race": getattr(u, "race", None),
            "current_week_of_pregnancy": getattr(u, "current_week_of_pregnancy", None),
        }
        return profile

    def _build_lifestyle(self) -> Dict[str, Any]:
        # Берём самую свежую запись (если нет явного timestamp — по id)
        q = UserLifeStyle.objects.filter(user=self.user).order_by("-id")
        ls = q.first()
        out = {}
        fields = tuple(
            dict.fromkeys(
                tuple(getattr(UserLifeStyle, "RISK_FIELDS", ()))
                + self.LIFESTYLE_CONTEXT_FIELDS
            )
        )
        if ls:
            for f in fields:
                out[f] = getattr(ls, f, None)
        else:
            for f in fields:
                out[f] = None
        return out

    def _build_aq(self) -> Dict[str, Any]:
        exp = (
            Exposure.objects.filter(user=self.user)
            .order_by("-timestamp")  # суточный агрегат, берём последний день
            .first()
        )
        latest_log = (
            AirExposureLog.objects.filter(user=self.user).order_by("-timestamp").first()
        )
        weather = {}
        if latest_log:
            weather = {
                "aqi": latest_log.aqi,
                "temperature": latest_log.temperature,
                "humidity": latest_log.humidity,
                "pressure": latest_log.pressure,
                "uvi": latest_log.uvi,
                "uvi_level": latest_log.uvi_level,
                "wind_speed": latest_log.wind_speed,
                "log_timestamp": latest_log.timestamp.isoformat(),
            }
        if not exp:
            return {
                "pollutants": {},
                "exposure_level": None,
                "date": None,
                **weather,
            }
        return {
            "pollutants": exp.pollutants or {},
            "exposure_level": exp.exposure_level,
            "date": exp.timestamp.isoformat(),
            **weather,
        }

    def _build_symptom_map(self, model_cls) -> Dict[str, bool]:
        """
        Возвращает словарь {симптом_нормализованный: True} за последние recent_hours.
        model_cls: UserMommySymptoms или UserBabySymptoms
        """
        cutoff = timezone.now() - timedelta(hours=self.recent_hours)
        qs: QuerySet = model_cls.objects.filter(user=self.user, recorded_at__gte=cutoff)
        names: Iterable[str] = qs.values_list("symptom__name", flat=True)

        result: Dict[str, bool] = {}
        for raw in names:
            norm = self._norm_symptom_name(raw)
            if norm:
                result[norm] = True
        return result

    def _norm_symptom_name(self, name: str) -> str:
        n = " ".join((name or "").strip().lower().split())
        return self.ALIASES.get(n, n)
