from datetime import datetime, timezone as dt_timezone
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from drf_spectacular.generators import SchemaGenerator
from rest_framework import status
from rest_framework.test import APITestCase

from api.models import (
    DailyAction,
    DailyPlan,
    DailyTask,
    HealthInsightSnapshot,
    RecommendationCompletion,
    UserDailyTaskCompletion,
    Wellbeing,
)
from api.services.daily_plan import (
    completion_states_for_plan,
    get_or_create_daily_plan,
    local_date_for_daily_plan,
    set_daily_action_completion,
)


User = get_user_model()


def recommendation_card(
    rule_id="rule.air",
    version=2,
    priority=20,
    category="air_quality",
    diet="Drink water.",
    activity="Walk indoors.",
    behavior="Close windows.",
    mental="",
):
    return {
        "rule_id": rule_id,
        "version": version,
        "priority": priority,
        "category": category,
        "title": "Air quality advice",
        "recommendation_diet": diet,
        "recommendation_activity": activity,
        "recommendation_behavior": behavior,
        "recommendation_mental": mental,
    }


class DailyPlanServiceTests(TestCase):
    def setUp(self):
        DailyTask.objects.all().delete()
        self.user = User.objects.create_user(
            email="daily-plan-service@example.com",
            password="testpass123",
            timezone="Europe/Prague",
        )
        self.task = DailyTask.objects.create(
            code="hydrate-plan",
            title="Stay hydrated",
            category="diet",
            sort_order=5,
        )
        self.snapshot = HealthInsightSnapshot.objects.create(
            user=self.user,
            recommendations=[recommendation_card()],
        )

    def _create_plan(self, plan_date="2026-09-05"):
        with patch(
            "recommendations.evaluator.get_or_create_fresh_snapshot",
            return_value=self.snapshot,
        ) as get_snapshot:
            plan = get_or_create_daily_plan(self.user, local_date=plan_date)
        return plan, get_snapshot

    def test_daily_plan_is_unique_per_user_and_local_date(self):
        DailyPlan.objects.create(
            user=self.user, local_date="2026-09-05", timezone="Europe/Prague"
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            DailyPlan.objects.create(
                user=self.user,
                local_date="2026-09-05",
                timezone="Europe/Prague",
            )

    def test_repeated_get_returns_same_plan_without_recomposition(self):
        first, first_snapshot_call = self._create_plan()
        action_ids = list(first.actions.values_list("id", flat=True))
        second, second_snapshot_call = self._create_plan()

        self.assertEqual(first.pk, second.pk)
        self.assertEqual(action_ids, list(second.actions.values_list("id", flat=True)))
        first_snapshot_call.assert_called_once()
        second_snapshot_call.assert_not_called()
        self.assertEqual(DailyPlan.objects.count(), 1)
        self.assertEqual(DailyAction.objects.count(), 4)

    @override_settings(HEALTH_INSIGHT_SNAPSHOT_FRESH_HOURS=2)
    def test_plan_composition_honors_configured_snapshot_freshness(self):
        with patch(
            "recommendations.evaluator.get_or_create_fresh_snapshot",
            return_value=self.snapshot,
        ) as get_snapshot:
            get_or_create_daily_plan(self.user, local_date="2026-09-08")

        get_snapshot.assert_called_once_with(
            self.user,
            fresh_for_hours=2,
            trigger_event="daily_plan",
        )

    def test_task_and_recommendation_fields_map_to_separate_actions(self):
        plan, _ = self._create_plan()
        task_action = plan.actions.get(source_type="task")
        recommendation_actions = plan.actions.filter(source_type="recommendation")

        self.assertEqual(task_action.domain, "nutrition")
        self.assertEqual(task_action.source_task_id, self.task.id)
        self.assertEqual(task_action.description, self.task.title)
        self.assertEqual(recommendation_actions.count(), 3)
        self.assertSetEqual(
            set(recommendation_actions.values_list("source_dimension", flat=True)),
            {"diet", "activity", "behavior"},
        )
        for action in recommendation_actions:
            self.assertEqual(action.source_snapshot_id, self.snapshot.id)
            self.assertEqual(action.source_rule_id, "rule.air")
            self.assertEqual(action.source_rule_version, 2)

    def test_mental_recommendation_maps_to_completable_mental_action(self):
        self.snapshot.recommendations = [
            recommendation_card(
                diet="",
                activity="",
                behavior="",
                mental="Take a calming pause.",
            )
        ]
        self.snapshot.save(update_fields=["recommendations"])

        plan, _ = self._create_plan()
        action = plan.actions.get(source_type="recommendation")

        self.assertEqual(action.domain, "mental")
        self.assertEqual(action.source_dimension, "mental")
        self.assertEqual(action.role, "primary")
        self.assertEqual(
            completion_states_for_plan(plan)[str(action.id)], "not_done"
        )

        self.assertEqual(set_daily_action_completion(action, "completed"), "completed")
        completion = RecommendationCompletion.objects.get(
            user=self.user,
            snapshot=self.snapshot,
            rule_id="rule.air",
            rule_version=2,
            dimension="mental",
        )
        self.assertEqual(completion.status, "done")

    def test_classification_is_deterministic_and_limited_by_domain(self):
        for index in range(2):
            DailyTask.objects.create(
                code=f"extra-behavior-{index}",
                title=f"Behavior {index}",
                category="behavior",
                sort_order=index,
            )
        DailyTask.objects.create(
            code="mental-plan",
            title="Take a mindful pause",
            category="mental",
            sort_order=3,
        )
        medical_snapshot = HealthInsightSnapshot.objects.create(
            user=self.user,
            recommendations=[
                recommendation_card(),
                recommendation_card(
                    rule_id="rule.medical",
                    category="medical",
                    diet="Contact your care team.",
                    activity="Rest until reviewed.",
                    behavior="Monitor symptoms.",
                ),
            ],
        )
        with patch(
            "recommendations.evaluator.get_or_create_fresh_snapshot",
            return_value=medical_snapshot,
        ):
            plan = get_or_create_daily_plan(self.user, local_date="2026-09-06")

        primaries = list(plan.actions.filter(role="primary"))
        self.assertLessEqual(len(primaries), 4)
        self.assertEqual(len({action.domain for action in primaries}), len(primaries))
        self.assertTrue(plan.actions.filter(role="additional").exists())
        support = plan.actions.filter(role="support")
        self.assertEqual(support.count(), 3)
        self.assertFalse(support.exclude(domain="service").exists())

    def test_plan_creation_is_atomic(self):
        with patch(
            "api.services.daily_plan._compose_plan",
            side_effect=RuntimeError("composition failed"),
        ):
            with self.assertRaises(RuntimeError):
                get_or_create_daily_plan(self.user, local_date="2026-09-07")

        self.assertFalse(
            DailyPlan.objects.filter(user=self.user, local_date="2026-09-07").exists()
        )

    @patch("api.services.daily_plan.timezone.now")
    def test_default_date_uses_user_timezone(self, now):
        now.return_value = datetime(2026, 9, 5, 23, 30, tzinfo=dt_timezone.utc)
        local_date, timezone_name = local_date_for_daily_plan(self.user)

        self.assertEqual(str(local_date), "2026-09-06")
        self.assertEqual(timezone_name, "Europe/Prague")

    def test_invalid_timezone_uses_application_timezone(self):
        self.user.timezone = "Invalid/Timezone"
        self.user.save(update_fields=["timezone"])

        _, timezone_name = local_date_for_daily_plan(self.user)

        self.assertEqual(timezone_name, "UTC")


class DailyPlanCompletionAdapterTests(TestCase):
    def setUp(self):
        DailyTask.objects.all().delete()
        self.user = User.objects.create_user(
            email="daily-plan-completion@example.com", password="testpass123"
        )
        self.task = DailyTask.objects.create(
            code="completion-task", title="Task", category="activity"
        )
        self.snapshot = HealthInsightSnapshot.objects.create(
            user=self.user,
            recommendations=[recommendation_card()],
        )
        with patch(
            "recommendations.evaluator.get_or_create_fresh_snapshot",
            return_value=self.snapshot,
        ):
            self.plan = get_or_create_daily_plan(
                self.user, local_date="2026-09-05"
            )

    def test_task_completion_true_and_false_mapping(self):
        action = self.plan.actions.get(source_type="task")
        self.assertEqual(completion_states_for_plan(self.plan)[str(action.id)], "not_done")

        completion = UserDailyTaskCompletion.objects.create(
            user=self.user,
            task=self.task,
            date=self.plan.local_date,
            completed=True,
        )
        self.assertEqual(completion_states_for_plan(self.plan)[str(action.id)], "completed")
        completion.completed = False
        completion.save(update_fields=["completed"])
        self.assertEqual(completion_states_for_plan(self.plan)[str(action.id)], "not_done")

        completion.skipped = True
        completion.save(update_fields=["skipped"])
        self.assertEqual(completion_states_for_plan(self.plan)[str(action.id)], "skipped")

    def test_recommendation_status_mapping_and_missing_completion(self):
        actions = {
            action.source_dimension: action
            for action in self.plan.actions.filter(source_type="recommendation")
        }
        self.assertEqual(
            completion_states_for_plan(self.plan)[str(actions["diet"].id)], "not_done"
        )
        for dimension, legacy_status, expected in (
            ("diet", "done", "completed"),
            ("activity", "skipped", "skipped"),
            ("behavior", "dismissed", "skipped"),
        ):
            RecommendationCompletion.objects.create(
                user=self.user,
                snapshot=self.snapshot,
                rule_id="rule.air",
                rule_version=2,
                dimension=dimension,
                status=legacy_status,
            )
            self.assertEqual(
                completion_states_for_plan(self.plan)[str(actions[dimension].id)],
                expected,
            )


class DailyPlanApiTests(APITestCase):
    def setUp(self):
        DailyTask.objects.all().delete()
        self.user = User.objects.create_user(
            email="daily-plan-api@example.com",
            password="testpass123",
            timezone="Europe/Prague",
        )
        DailyTask.objects.create(
            code="api-task", title="API task", category="mental", sort_order=1
        )
        self.snapshot = HealthInsightSnapshot.objects.create(
            user=self.user,
            recommendations=[recommendation_card(diet="", activity="", behavior="")],
        )

    def test_authentication_is_required(self):
        response = self.client.get(reverse("daily-plan"))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    @patch("recommendations.evaluator.get_or_create_fresh_snapshot")
    def test_response_contract_and_date_query(self, get_snapshot):
        get_snapshot.return_value = self.snapshot
        self.client.force_authenticate(self.user)

        response = self.client.get(reverse("daily-plan"), {"date": "2026-09-05"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["date"], "2026-09-05")
        self.assertEqual(response.data["timezone"], "Europe/Prague")
        self.assertEqual(len(response.data["primary_actions"]), 1)
        action = response.data["primary_actions"][0]
        self.assertSetEqual(
            set(action),
            {
                "id",
                "domain",
                "title",
                "description",
                "timing",
                "duration_minutes",
                "context",
                "completion_state",
            },
        )
        self.assertEqual(action["completion_state"], "not_done")
        self.assertEqual(response.data["additional_actions"], [])
        self.assertEqual(response.data["support_actions"], [])

    def test_invalid_date_returns_400(self):
        self.client.force_authenticate(self.user)
        response = self.client.get(reverse("daily-plan"), {"date": "not-a-date"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_legacy_task_and_recommendation_endpoints_are_unchanged(self):
        self.client.force_authenticate(self.user)
        task_response = self.client.get(reverse("daily-tasks"))
        completion_response = self.client.get(reverse("recommendation-completion"))

        self.assertEqual(task_response.status_code, status.HTTP_200_OK)
        self.assertEqual(completion_response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            set(task_response.data[0]), {"code", "title", "category", "sort_order"}
        )

    def test_openapi_has_explicit_daily_plan_response(self):
        schema = SchemaGenerator().get_schema(request=None, public=True)
        operation = schema["paths"]["/api/daily-plan/"]["get"]
        response_schema = operation["responses"]["200"]["content"][
            "application/json"
        ]["schema"]
        component_name = response_schema["$ref"].rsplit("/", 1)[-1]
        properties = schema["components"]["schemas"][component_name]["properties"]

        self.assertSetEqual(
            set(properties),
            {
                "date",
                "timezone",
                "primary_actions",
                "additional_actions",
                "support_actions",
            },
        )
        primary_items = properties["primary_actions"]["items"]
        primary_component = primary_items["$ref"].rsplit("/", 1)[-1]
        self.assertIn(
            "completion_state",
            schema["components"]["schemas"][primary_component]["properties"],
        )


class DailyPlanWellbeingIntegrationTests(APITestCase):
    def setUp(self):
        DailyTask.objects.all().delete()
        self.user = User.objects.create_user(
            email="daily-plan-wellbeing@example.com",
            password="testpass123",
            timezone="UTC",
        )
        DailyTask.objects.create(
            code="wellbeing-fallback-task",
            title="Fallback task",
            category="behavior",
        )
        self.nervous = Wellbeing.objects.get(code="nervous")
        self.today = timezone.localdate().isoformat()
        self.client.force_authenticate(self.user)

    @staticmethod
    def _actions(response):
        return response.data["primary_actions"] + response.data["additional_actions"]

    def _post_nervous(self):
        return self.client.post(
            reverse("wellbeing-log"),
            {
                "date": self.today,
                "mood_ids": [self.nervous.id],
                "feeling_ids": [],
            },
            format="json",
        )

    def test_missing_wellbeing_returns_a_valid_plan_without_mental_action(self):
        response = self.client.get(reverse("daily-plan"), {"date": self.today})

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertTrue(self._actions(response))
        self.assertFalse(
            any(action["domain"] == "mental" for action in self._actions(response))
        )

    def test_wellbeing_before_plan_adds_a_mental_action(self):
        wellbeing_response = self._post_nervous()
        self.assertEqual(
            wellbeing_response.status_code,
            status.HTTP_201_CREATED,
            wellbeing_response.data,
        )

        response = self.client.get(reverse("daily-plan"), {"date": self.today})

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        mental_actions = [
            action for action in self._actions(response) if action["domain"] == "mental"
        ]
        self.assertEqual(len(mental_actions), 1)
        self.assertEqual(mental_actions[0]["completion_state"], "not_done")

    def test_wellbeing_after_plan_does_not_mutate_the_existing_plan(self):
        first = self.client.get(reverse("daily-plan"), {"date": self.today})
        first_actions = self._actions(first)
        first_ids = [action["id"] for action in first_actions]
        self.assertFalse(any(action["domain"] == "mental" for action in first_actions))

        wellbeing_response = self._post_nervous()
        self.assertEqual(wellbeing_response.status_code, status.HTTP_201_CREATED)
        second = self.client.get(reverse("daily-plan"), {"date": self.today})

        self.assertEqual(second.status_code, status.HTTP_200_OK, second.data)
        self.assertEqual([action["id"] for action in self._actions(second)], first_ids)
        self.assertFalse(
            any(action["domain"] == "mental" for action in self._actions(second))
        )


class DailyActionCompletionApiTests(APITestCase):
    def setUp(self):
        DailyTask.objects.all().delete()
        self.user = User.objects.create_user(
            email="daily-action-completion@example.com", password="testpass123"
        )
        self.other_user = User.objects.create_user(
            email="daily-action-other@example.com", password="testpass123"
        )
        self.task = DailyTask.objects.create(
            code="action-completion-task",
            title="Action completion task",
            category="mental",
        )
        self.snapshot = HealthInsightSnapshot.objects.create(
            user=self.user,
            recommendations=[recommendation_card()],
        )
        with patch(
            "recommendations.evaluator.get_or_create_fresh_snapshot",
            return_value=self.snapshot,
        ):
            self.plan = get_or_create_daily_plan(
                self.user, local_date="2026-09-05"
            )
        self.client.force_authenticate(self.user)

    def _url(self, action):
        return reverse("daily-action-completion", args=[action.id])

    def _patch_state(self, action, completion_state):
        return self.client.patch(
            self._url(action),
            {"completion_state": completion_state},
            format="json",
        )

    def test_task_supports_all_completion_state_transitions(self):
        action = self.plan.actions.get(source_type="task")

        for requested, expected_flags in (
            ("completed", (True, False)),
            ("skipped", (False, True)),
            ("not_done", (False, False)),
        ):
            response = self._patch_state(action, requested)
            self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
            self.assertEqual(response.data["id"], str(action.id))
            self.assertEqual(response.data["completion_state"], requested)
            completion = UserDailyTaskCompletion.objects.get(
                user=self.user,
                task=self.task,
                date=self.plan.local_date,
            )
            self.assertEqual(
                (completion.completed, completion.skipped), expected_flags
            )
            self.assertEqual(
                completion_states_for_plan(self.plan)[str(action.id)], requested
            )

    def test_repeating_same_state_is_idempotent(self):
        action = self.plan.actions.get(source_type="task")

        first = self._patch_state(action, "skipped")
        second = self._patch_state(action, "skipped")

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(
            UserDailyTaskCompletion.objects.filter(
                user=self.user,
                task=self.task,
                date=self.plan.local_date,
            ).count(),
            1,
        )

    def test_recommendation_supports_all_completion_state_transitions(self):
        action = self.plan.actions.filter(source_type="recommendation").first()

        for requested, legacy_status in (
            ("completed", "done"),
            ("skipped", "skipped"),
        ):
            response = self._patch_state(action, requested)
            self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
            completion = RecommendationCompletion.objects.get(
                user=self.user,
                snapshot_id=action.source_snapshot_id,
                rule_id=action.source_rule_id,
                rule_version=action.source_rule_version,
                dimension=action.source_dimension,
            )
            self.assertEqual(completion.status, legacy_status)

        response = self._patch_state(action, "not_done")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertFalse(
            RecommendationCompletion.objects.filter(
                user=self.user,
                snapshot_id=action.source_snapshot_id,
                rule_id=action.source_rule_id,
                rule_version=action.source_rule_version,
                dimension=action.source_dimension,
            ).exists()
        )

    def test_support_action_is_read_only(self):
        action = self.plan.actions.filter(source_type="recommendation").first()
        action.role = "support"
        action.domain = "service"
        action.save(update_fields=["role", "domain"])

        response = self._patch_state(action, "completed")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data["detail"],
            "Support actions do not support completion updates.",
        )

    def test_action_from_another_user_is_not_found(self):
        action = self.plan.actions.get(source_type="task")
        self.client.force_authenticate(self.other_user)

        response = self._patch_state(action, "completed")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(UserDailyTaskCompletion.objects.exists())

    def test_invalid_state_is_rejected(self):
        action = self.plan.actions.get(source_type="task")

        response = self._patch_state(action, "dismissed")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("completion_state", response.data)

    def test_authentication_is_required(self):
        action = self.plan.actions.get(source_type="task")
        self.client.force_authenticate(user=None)

        response = self._patch_state(action, "completed")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_legacy_task_completion_clears_skipped_state(self):
        action = self.plan.actions.get(source_type="task")
        self._patch_state(action, "skipped")

        response = self.client.post(
            reverse("task-completion"),
            {"date": str(self.plan.local_date), "tasks": [self.task.code]},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        completion = UserDailyTaskCompletion.objects.get(
            user=self.user, task=self.task, date=self.plan.local_date
        )
        self.assertTrue(completion.completed)
        self.assertFalse(completion.skipped)

    def test_openapi_documents_completion_endpoint_and_states(self):
        schema = SchemaGenerator().get_schema(request=None, public=True)
        operation = schema["paths"][
            "/api/daily-plan/actions/{action_id}/completion/"
        ]["patch"]
        request_schema = operation["requestBody"]["content"]["application/json"][
            "schema"
        ]
        state_schema = request_schema["properties"]["completion_state"]

        self.assertSetEqual(
            set(state_schema["enum"]),
            {"completed", "skipped", "not_done"},
        )
        self.assertEqual(request_schema["required"], ["completion_state"])
