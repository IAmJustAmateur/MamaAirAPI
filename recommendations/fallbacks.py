# recommendations/fallbacks.py
from __future__ import annotations
from datetime import timedelta, timezone as dt_tz
from typing import Dict, Any, List
from django.utils import timezone
from .const import ENGINE_VERSION


def _trimester(week: int | None) -> int | None:
    if not week or week <= 0:
        return None
    if week <= 13:
        return 1
    if week <= 27:
        return 2
    return 3


WEEKLY_TIPS = {
    1: [
        (
            "tip.walk.light",
            "Short, easy walks (10–20 min) most days can help mood and sleep.",
        ),
        ("tip.hydration", "Keep steady hydration throughout the day."),
    ],
    2: [
        ("tip.walk.30", "Aim for 20–30 minutes of comfortable walking today."),
        ("tip.stretch", "Stand and stretch 2–3 minutes each hour."),
    ],
    3: [
        ("tip.pace", "Pace the day: alternate activity with short rests."),
        ("tip.sleep", "Protect your bedtime routine for better sleep quality."),
    ],
}

WORK_TIPS = {
    "Desk": (
        "tip.desk.stretch",
        "Every hour: stand up, roll shoulders, gentle neck stretch.",
    ),
    "Standing": (
        "tip.standing.rest",
        "Plan brief seated rests to reduce swelling and back strain.",
    ),
    "Physical": (
        "tip.physical.pace",
        "Break tasks into shorter bouts with hydration breaks.",
    ),
    "Care": ("tip.care.back", "Mind posture; short back/hip stretches help."),
    "Field": ("tip.field.shade", "Prefer shade and cooler hours for outdoor errands."),
    "Domestic": (
        "tip.dom.schedule",
        "Spread chores across the day; avoid long continuous bouts.",
    ),
    "Night Shift": (
        "tip.night.light",
        "Seek morning daylight; keep naps short (20–30 min).",
    ),
}


def _pick_by_day(options: List[tuple[str, str]], user_id: int) -> tuple[str, str]:
    seed = (user_id * 1315423911) ^ int(timezone.localdate().strftime("%Y%m%d"))
    idx = seed % max(1, len(options))
    return options[idx]


def build_fallback_recommendations(user, ctx: Dict[str, Any]) -> List[Dict[str, Any]]:
    recs: List[Dict[str, Any]] = []
    now = timezone.now()

    # 1) Data completeness nudges (if anything important is missing)
    lifestyle = ctx.get("lifestyle", {})
    missing: list[str] = []
    if lifestyle.get("average_sleep_hours") is None:
        missing.append("sleep hours")
    if lifestyle.get("activity_duration_minutes") is None:
        missing.append("weekly activity")
    if missing:
        recs.append(
            {
                "id": "info.complete_data.v1",
                "severity": "info",
                "title": "Complete your data",
                "message": f"Add your {', '.join(missing)} to tailor insights.",
                "category": "general",
                "ttl_hours": 72,
                "expires_at": (now + timedelta(hours=72))
                .astimezone(dt_tz.utc)
                .isoformat(),
                "sources": ["engine"],
                "engine_version": ENGINE_VERSION,
                "priority": 72,
                "rule_id": "fallback.complete_data",
                "version": 1,
            }
        )

    # 2) Preventive weekly tip (by trimester)
    week = ctx.get("profile", {}).get("week_of_pregnancy")
    tri = _trimester(week)
    if tri in WEEKLY_TIPS:
        tip_id, tip_msg = _pick_by_day(WEEKLY_TIPS[tri], user.id)
        recs.append(
            {
                "id": f"{tip_id}.v1",
                "severity": "info",
                "title": "Today’s preventive tip",
                "message": tip_msg,
                "category": "lifestyle",
                "ttl_hours": 24,
                "expires_at": (now + timedelta(hours=24))
                .astimezone(dt_tz.utc)
                .isoformat(),
                "sources": ["engine"],
                "engine_version": ENGINE_VERSION,
                "priority": 74,
                "rule_id": "fallback.weekly_tip",
                "version": 1,
            }
        )

    # 3) Work-type tip (if present)
    work_type = lifestyle.get("work_type")
    if work_type in WORK_TIPS:
        wt_id, wt_msg = WORK_TIPS[work_type]
        recs.append(
            {
                "id": f"{wt_id}.v1",
                "severity": "info",
                "title": "Workday tip",
                "message": wt_msg,
                "category": "lifestyle",
                "ttl_hours": 24,
                "expires_at": (now + timedelta(hours=24))
                .astimezone(dt_tz.utc)
                .isoformat(),
                "sources": ["engine"],
                "engine_version": ENGINE_VERSION,
                "priority": 75,
                "rule_id": "fallback.work_tip",
                "version": 1,
            }
        )

    # 4) Kick count check-in (>=28 weeks)
    if (week or 0) >= 28:
        recs.append(
            {
                "id": "info.kick_count.v1",
                "severity": "info",
                "title": "Kick count check-in",
                "message": "Pick a usual time and count 10 movements today. If you notice a clear reduction, contact your doctor.",
                "category": "medical",
                "ttl_hours": 24,
                "expires_at": (now + timedelta(hours=24))
                .astimezone(dt_tz.utc)
                .isoformat(),
                "sources": ["engine"],
                "engine_version": ENGINE_VERSION,
                "priority": 76,
                "rule_id": "fallback.kick_count",
                "version": 1,
            }
        )

    # 5) Final cover card (only if still nothing else)
    if not recs:
        recs.append(
            {
                "id": "info.monitoring.v1",
                "severity": "info",
                "title": "No urgent alerts detected",
                "message": "We found no urgent alerts right now. Keep logging symptoms and we’ll keep monitoring.",
                "category": "general",
                "ttl_hours": 24,
                "expires_at": (now + timedelta(hours=24))
                .astimezone(dt_tz.utc)
                .isoformat(),
                "sources": ["engine"],
                "engine_version": ENGINE_VERSION,
                "priority": 79,
                "rule_id": "fallback.monitoring",
                "version": 1,
            }
        )

    recs.sort(key=lambda x: x["priority"])
    return recs
