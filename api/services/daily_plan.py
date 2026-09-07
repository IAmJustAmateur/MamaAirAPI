from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from api.models import (
    DailyAction,
    DailyPlan,
    DailyTask,
    RecommendationCompletion,
    UserDailyTaskCompletion,
)


DOMAIN_BY_TASK_CATEGORY = {
    "diet": "nutrition",
    "activity": "activity",
    "behavior": "behavior",
    "mental": "mental",
}
RECOMMENDATION_FIELDS = (
    ("recommendation_diet", "nutrition", "diet"),
    ("recommendation_activity", "activity", "activity"),
    ("recommendation_behavior", "behavior", "behavior"),
)
MAIN_DOMAINS = {"nutrition", "activity", "behavior", "mental"}
COMPLETION_STATES = {"completed", "skipped", "not_done"}


class DailyActionCompletionNotAllowed(ValueError):
    pass


@dataclass(frozen=True)
class ActionCandidate:
    stable_key: str
    domain: str
    title: str
    description: str
    source_type: str
    source_task_id: int | None = None
    source_snapshot_id: int | None = None
    source_rule_id: str | None = None
    source_rule_version: int | None = None
    source_dimension: str | None = None
    priority: int = 0
    role: str = "additional"


def _timezone_for_user(user) -> tuple[ZoneInfo, str]:
    timezone_name = (getattr(user, "timezone", None) or settings.TIME_ZONE).strip()
    try:
        return ZoneInfo(timezone_name), timezone_name
    except (ZoneInfoNotFoundError, ValueError):
        fallback_name = settings.TIME_ZONE
        try:
            return ZoneInfo(fallback_name), fallback_name
        except (ZoneInfoNotFoundError, ValueError):
            return ZoneInfo("UTC"), "UTC"


def local_date_for_daily_plan(user) -> tuple[date, str]:
    user_timezone, timezone_name = _timezone_for_user(user)
    return timezone.localtime(timezone.now(), user_timezone).date(), timezone_name


def _task_candidates() -> list[ActionCandidate]:
    candidates = []
    for task in DailyTask.objects.filter(is_active=True).order_by(
        "sort_order", "title", "id"
    ):
        candidates.append(
            ActionCandidate(
                stable_key=f"task:{task.id}",
                domain=DOMAIN_BY_TASK_CATEGORY[task.category],
                title=task.title,
                description=task.title,
                source_type="task",
                source_task_id=task.id,
                priority=task.sort_order,
            )
        )
    return candidates


def _recommendation_candidates(snapshot) -> list[ActionCandidate]:
    candidates = []
    for card_index, recommendation in enumerate(snapshot.recommendations or []):
        rule_id = recommendation.get("rule_id")
        version = recommendation.get("version")
        if not rule_id or version is None:
            continue
        priority = recommendation.get("priority", 100)
        try:
            priority = int(priority)
        except (TypeError, ValueError):
            priority = 100
        is_service = recommendation.get("category") == "medical"
        for dimension_index, (field, domain, dimension) in enumerate(
            RECOMMENDATION_FIELDS
        ):
            description = recommendation.get(field)
            if not isinstance(description, str) or not description.strip():
                continue
            candidates.append(
                ActionCandidate(
                    stable_key=(
                        f"recommendation:{snapshot.id}:{rule_id}:{version}:{dimension}"
                    ),
                    domain="service" if is_service else domain,
                    role="support" if is_service else "additional",
                    title=recommendation.get("title") or description.strip(),
                    description=description.strip(),
                    source_type="recommendation",
                    source_snapshot_id=snapshot.id,
                    source_rule_id=str(rule_id),
                    source_rule_version=int(version),
                    source_dimension=dimension,
                    priority=priority * 10 + dimension_index + card_index,
                )
            )
    return candidates


def _classify(candidates: list[ActionCandidate]) -> list[ActionCandidate]:
    ordered = sorted(
        candidates,
        key=lambda item: (item.priority, item.source_type, item.stable_key),
    )
    primary_domains = set()
    classified = []
    for item in ordered:
        role = item.role
        if role != "support":
            if item.domain in MAIN_DOMAINS and item.domain not in primary_domains:
                role = "primary"
                primary_domains.add(item.domain)
            else:
                role = "additional"
        classified.append(
            ActionCandidate(**{**item.__dict__, "role": role})
        )
    return classified


def _compose_plan(plan: DailyPlan) -> None:
    from recommendations.evaluator import get_or_create_fresh_snapshot

    snapshot = get_or_create_fresh_snapshot(
        plan.user,
        fresh_for_hours=settings.HEALTH_INSIGHT_SNAPSHOT_FRESH_HOURS,
        trigger_event="daily_plan",
    )
    candidates = _classify(_task_candidates() + _recommendation_candidates(snapshot))
    DailyAction.objects.bulk_create(
        [
            DailyAction(
                plan=plan,
                stable_key=item.stable_key,
                domain=item.domain,
                role=item.role,
                title=item.title,
                description=item.description,
                sort_order=index,
                source_type=item.source_type,
                source_task_id=item.source_task_id,
                source_snapshot_id=item.source_snapshot_id,
                source_rule_id=item.source_rule_id,
                source_rule_version=item.source_rule_version,
                source_dimension=item.source_dimension,
            )
            for index, item in enumerate(candidates)
        ]
    )


def get_or_create_daily_plan(user, local_date: date | None = None) -> DailyPlan:
    default_date, timezone_name = local_date_for_daily_plan(user)
    plan_date = local_date or default_date
    existing = DailyPlan.objects.filter(user=user, local_date=plan_date).first()
    if existing:
        return existing

    try:
        with transaction.atomic():
            plan = DailyPlan.objects.create(
                user=user,
                local_date=plan_date,
                timezone=timezone_name,
            )
            _compose_plan(plan)
            return plan
    except IntegrityError:
        concurrent_plan = DailyPlan.objects.filter(
            user=user, local_date=plan_date
        ).first()
        if concurrent_plan:
            return concurrent_plan
        raise


def completion_states_for_plan(plan: DailyPlan) -> dict[str, str]:
    actions = list(plan.actions.all())
    task_ids = [a.source_task_id for a in actions if a.source_type == "task"]
    task_completions = {
        row.task_id: (row.completed, row.skipped)
        for row in UserDailyTaskCompletion.objects.filter(
            user=plan.user,
            date=plan.local_date,
            task_id__in=task_ids,
        )
    }

    snapshot_ids = {
        a.source_snapshot_id for a in actions if a.source_type == "recommendation"
    }
    recommendation_completions = {
        (row.snapshot_id, row.rule_id, row.rule_version, row.dimension): row.status
        for row in RecommendationCompletion.objects.filter(
            user=plan.user,
            snapshot_id__in=snapshot_ids,
        )
    }

    states = {}
    for action in actions:
        if action.source_type == "task":
            completed, skipped = task_completions.get(
                action.source_task_id, (False, False)
            )
            states[str(action.id)] = (
                "skipped" if skipped else ("completed" if completed else "not_done")
            )
            continue
        status = recommendation_completions.get(
            (
                action.source_snapshot_id,
                action.source_rule_id,
                action.source_rule_version,
                action.source_dimension,
            )
        )
        states[str(action.id)] = {
            "done": "completed",
            "skipped": "skipped",
            "dismissed": "skipped",
        }.get(status, "not_done")
    return states


def set_daily_action_completion(action: DailyAction, state: str) -> str:
    if state not in COMPLETION_STATES:
        raise ValueError(f"Unsupported completion state: {state}")
    if action.role == "support":
        raise DailyActionCompletionNotAllowed(
            "Support actions do not support completion updates."
        )

    with transaction.atomic():
        if action.source_type == "task":
            UserDailyTaskCompletion.objects.update_or_create(
                user=action.plan.user,
                task_id=action.source_task_id,
                date=action.plan.local_date,
                defaults={
                    "completed": state == "completed",
                    "skipped": state == "skipped",
                },
            )
            return state

        lookup = {
            "user": action.plan.user,
            "snapshot_id": action.source_snapshot_id,
            "rule_id": action.source_rule_id,
            "rule_version": action.source_rule_version,
            "dimension": action.source_dimension,
        }
        if state == "not_done":
            RecommendationCompletion.objects.filter(**lookup).delete()
        else:
            RecommendationCompletion.objects.update_or_create(
                **lookup,
                defaults={"status": "done" if state == "completed" else "skipped"},
            )
    return state
