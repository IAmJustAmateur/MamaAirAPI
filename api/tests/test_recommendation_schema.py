import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.urls import reverse
from drf_spectacular.generators import SchemaGenerator
from rest_framework import status
from rest_framework.test import APITestCase

from api.models import HealthInsightSnapshot, RecommendationCompletion
from api.serializers import (
    HealthInsightResponseSerializer,
    RecommendationCompletionSerializer,
    RecommendationCompletionValidationErrorSerializer,
    RecommendationSerializer,
)


User = get_user_model()


class RecommendationSerializerContractTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="recommendation-schema@example.com",
            password="testpass123",
        )
        self.recommendation = {
            "id": "alert.pm25.daily.v1",
            "rule_id": "alert.pm25.daily",
            "version": 1,
            "severity": "moderate",
            "category": "air_quality",
            "priority": 20,
            "title": "PM2.5 is high",
            "alert": "Limit outdoor time today.",
            "recommendation_diet": "Drink enough water.",
            "recommendation_activity": "Prefer indoor activity.",
            "recommendation_behavior": "Keep windows closed during peaks.",
            "ttl_hours": 12,
            "expires_at": "2026-08-20T08:00:00Z",
            "sources": ["engine"],
            "engine_version": "receng-mvp-0.1",
        }
        self.snapshot = HealthInsightSnapshot.objects.create(
            user=self.user,
            recommendations=[self.recommendation],
        )

    def test_representative_recommendation_validates_against_contract(self):
        serializer = RecommendationSerializer(data=self.recommendation)

        self.assertTrue(serializer.is_valid(), serializer.errors)

        response = HealthInsightResponseSerializer(self.snapshot).data
        self.assertEqual(response["recommendations"][0]["rule_id"], "alert.pm25.daily")
        self.assertEqual(response["recommendations"][0]["priority"], 20)

    @patch("recommendations.evaluator.get_or_create_fresh_snapshot")
    def test_advice_runtime_payload_remains_unchanged(self, get_snapshot):
        get_snapshot.return_value = self.snapshot
        self.client.force_authenticate(self.user)

        response = self.client.get(reverse("advice"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["recommendations"], [self.recommendation])
        self.assertNotIn("message", response.data["recommendations"][0])


class RecommendationCompletionSerializerContractTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="recommendation-completion-schema@example.com",
            password="testpass123",
        )
        self.snapshot = HealthInsightSnapshot.objects.create(
            user=self.user,
            recommendations=[{"id": "alert.pm25.daily.v1"}],
        )

    def test_representative_completion_validates_against_contract(self):
        completion = RecommendationCompletion.objects.create(
            user=self.user,
            snapshot=self.snapshot,
            rule_id="alert.pm25.daily",
            rule_version=1,
            dimension="behavior",
            status="done",
        )
        payload = RecommendationCompletionSerializer(completion).data

        serializer = RecommendationCompletionSerializer(data=payload)
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_representative_validation_error_validates_against_contract(self):
        payload = {"snapshot_id": ["Snapshot not found for this user."]}
        serializer = RecommendationCompletionValidationErrorSerializer(data=payload)

        self.assertTrue(serializer.is_valid(), serializer.errors)


class RecommendationOpenAPIContractTests(APITestCase):
    @staticmethod
    def _resolve(schema, value):
        if "$ref" in value:
            name = value["$ref"].rsplit("/", 1)[-1]
            return schema["components"]["schemas"][name]
        if "allOf" in value and len(value["allOf"]) == 1:
            return RecommendationOpenAPIContractTests._resolve(
                schema, value["allOf"][0]
            )
        return value

    def test_advice_schema_has_typed_recommendation_items(self):
        schema = SchemaGenerator().get_schema(request=None, public=True)
        operation = schema["paths"]["/api/advice/"]["get"]
        response_schema = self._resolve(
            schema,
            operation["responses"]["200"]["content"]["application/json"][
                "schema"
            ],
        )

        recommendations = response_schema["properties"]["recommendations"]
        self.assertEqual(recommendations["type"], "array")
        recommendation = self._resolve(schema, recommendations["items"])
        self.assertEqual(recommendation["required"], ["id"])
        self.assertEqual(recommendation["properties"]["id"]["type"], "string")
        self.assertEqual(
            recommendation["properties"]["priority"]["type"], "integer"
        )
        self.assertEqual(
            recommendation["properties"]["sources"]["items"]["type"],
            "string",
        )

    def test_completion_schema_types_list_upsert_and_validation_error(self):
        schema = SchemaGenerator().get_schema(request=None, public=True)
        operation = schema["paths"]["/api/recommendation-completion/"]

        list_schema = operation["get"]["responses"]["200"]["content"][
            "application/json"
        ]["schema"]
        self.assertEqual(list_schema["type"], "array")
        completion = self._resolve(schema, list_schema["items"])
        self.assertEqual(
            completion["properties"]["snapshot_id"]["type"], "integer"
        )

        post_responses = operation["post"]["responses"]
        self.assertIn("200", post_responses)
        self.assertIn("201", post_responses)
        self.assertIn("400", post_responses)

        error_schema = self._resolve(
            schema,
            post_responses["400"]["content"]["application/json"]["schema"],
        )
        snapshot_errors = error_schema["properties"]["snapshot_id"]
        self.assertEqual(snapshot_errors["type"], "array")
        self.assertEqual(snapshot_errors["items"]["type"], "string")

    def test_public_schema_exposes_mobile_contract_only(self):
        schema = SchemaGenerator().get_schema(request=None, public=True)
        paths = schema["paths"]

        self.assertNotIn("/api/auth/firebase/", paths)
        self.assertNotIn("/api/auth/register/", paths)
        self.assertFalse(any(path.startswith("/api/debug/") for path in paths))
        self.assertFalse(any(path.startswith("/demo/") for path in paths))
        self.assertEqual(
            schema["components"]["securitySchemes"]["jwtAuth"],
            {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"},
        )

    def test_public_schema_contains_no_cyrillic_text(self):
        schema = SchemaGenerator().get_schema(request=None, public=True)
        rendered = json.dumps(schema, ensure_ascii=False)
        self.assertNotRegex(rendered, r"[А-Яа-яЁё]")

    def test_checklist_ids_are_required_non_nullable_integers(self):
        schema = SchemaGenerator().get_schema(request=None, public=True)
        checklist_item = schema["components"]["schemas"]["ChecklistItemSchema"]
        self.assertIn("id", checklist_item["required"])
        self.assertEqual(checklist_item["properties"]["id"], {"type": "integer"})
