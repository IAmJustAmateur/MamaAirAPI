# recommendations/evaluator.py
from __future__ import annotations
from datetime import timedelta, timezone as dt_tz
from django.utils import timezone
from typing import List, Dict, Any

from .context import EvalContextBuilder
from .models import RecommendationRule

from api.models import HealthInsightSnapshot
from .const import ENGINE_VERSION
from .fallbacks import build_fallback_recommendations


def evaluate_recommendations(user) -> List[Dict[str, Any]]:
    """
    Собирает контекст и прогоняет активные правила через eval-песочницу.
    Возвращает список карточек рекомендаций (в порядке приоритета).
    """
    ctx = EvalContextBuilder(user, recent_hours=24).build()
    safe_globals = {"__builtins__": {}}

    recs: List[Dict[str, Any]] = []
    # queryset уже отсортирован по priority (см. models.Meta.ordering)
    for r in RecommendationRule.objects.active():
        try:
            matched = bool(eval(r.condition, safe_globals, ctx))
        except Exception:
            matched = False  # можно логировать

        if not matched:
            continue

        recs.append(
            {
                "id": f"{r.rule_id}.v{r.version}",
                "severity": r.severity,
                "title": r.title,
                "alert": r.alert,
                "recommendation_diet": r.recommendation_diet,
                "recommendation_activity": r.recommendation_activity,
                "recommendation_behavior": r.recommendation_behavior,
                "recommendation_mental": r.recommendation_mental,
                "category": r.category,
                "ttl_hours": r.ttl_hours,
                "sources": ["engine"],
                "engine_version": ENGINE_VERSION,
                # полезно для отладки/клиента:
                "priority": r.priority,
                "rule_id": r.rule_id,
                "version": r.version,
            }
        )

    # порядок уже по приоритету, но на всякий — гарантируем:
    recs.sort(key=lambda x: x["priority"])
    # Fallbacks if nothing matched
    if not recs:
        recs = build_fallback_recommendations(user, ctx)
    return recs


def generate_health_insight_snapshot(
    user, trigger_event: str = "manual"
) -> HealthInsightSnapshot:
    """
    Создаёт новый снапшот рекомендаций для пользователя.
    """
    recs = evaluate_recommendations(user)
    now = timezone.now()
    for item in recs:
        ttl = item.get("ttl_hours") or 24
        item["expires_at"] = (
            (now + timedelta(hours=ttl)).astimezone(dt_tz.utc).isoformat()
        )

    snapshot = HealthInsightSnapshot.objects.create(
        user=user,
        recommendations=recs,
        source="engine",
        trigger_event=trigger_event,
        engine_version=ENGINE_VERSION,
    )
    return snapshot


def get_or_create_fresh_snapshot(
    user, fresh_for_hours: int = 6, trigger_event: str = "login"
) -> HealthInsightSnapshot:
    """
    Возвращает последний снапшот; если его нет или он устарел — создаёт новый.
    """
    snap = user.health_insights.order_by("-created_at").first()
    if (
        snap
        and (timezone.now() - snap.created_at).total_seconds() < fresh_for_hours * 3600
    ):
        return snap
    return generate_health_insight_snapshot(user, trigger_event=trigger_event)
