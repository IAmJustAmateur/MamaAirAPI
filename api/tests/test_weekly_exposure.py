from django.contrib.auth import get_user_model
from django.urls import reverse
from drf_spectacular.generators import SchemaGenerator
from rest_framework import status
from rest_framework.test import APITestCase

from api.models import WeeklyExposure
from api.serializers import ErrorSerializer, WeeklyExposureResponseSerializer


User = get_user_model()


class WeeklyExposureAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="weekly-exposure@example.com",
            password="testpass123",
        )
        self.url = reverse("exposure-per-weeks")

    def test_requires_authentication(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertIn("detail", response.data)
        error_serializer = ErrorSerializer(data=response.json())
        self.assertTrue(error_serializer.is_valid(), error_serializer.errors)

    def test_returns_existing_dynamic_week_map(self):
        WeeklyExposure.objects.create(
            user=self.user,
            pregnancy_week=12,
            exposure_level="Moderate",
        )
        WeeklyExposure.objects.create(
            user=self.user,
            pregnancy_week=13,
            exposure_level="Unhealthy",
        )
        self.client.force_authenticate(self.user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data,
            {
                13: {"level": "Unhealthy"},
                12: {"level": "Moderate"},
            },
        )
        WeeklyExposureResponseSerializer().run_validation(response.json())

    def test_returns_empty_object_when_no_weekly_exposure_exists(self):
        self.client.force_authenticate(self.user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, {})
        WeeklyExposureResponseSerializer().run_validation(response.json())


class WeeklyExposureOpenAPITests(APITestCase):
    @staticmethod
    def _resolve(schema, value):
        if "$ref" not in value:
            return value
        component_name = value["$ref"].rsplit("/", 1)[-1]
        return schema["components"]["schemas"][component_name]

    def test_schema_types_week_map_empty_partial_and_authentication_responses(self):
        schema = SchemaGenerator().get_schema(request=None, public=True)
        operation = schema["paths"]["/api/exposure-per-weeks/"]["get"]
        responses = operation["responses"]

        self.assertIn("200", responses)
        self.assertIn("401", responses)

        response_schema = responses["200"]["content"]["application/json"]["schema"]
        response_schema = self._resolve(schema, response_schema)
        self.assertEqual(response_schema["type"], "object")
        self.assertIn("additionalProperties", response_schema)

        item_schema = self._resolve(schema, response_schema["additionalProperties"])
        self.assertIn("level", item_schema["required"])
        level_schema = self._resolve(schema, item_schema["properties"]["level"])
        self.assertEqual(
            level_schema["enum"],
            [
                "Clean",
                "Very Good",
                "Moderate",
                "Acceptable",
                "Unhealthy",
                "High",
                "Hazardous",
                "Extreme",
            ],
        )

        examples = responses["200"]["content"]["application/json"]["examples"]
        self.assertEqual(examples["EmptyResult"]["value"], {})
        self.assertEqual(
            examples["PartialResult"]["value"],
            {"13": {"level": "Unhealthy"}},
        )

        error_schema = responses["401"]["content"]["application/json"]["schema"]
        error_schema = self._resolve(schema, error_schema)
        self.assertIn("detail", error_schema["required"])
