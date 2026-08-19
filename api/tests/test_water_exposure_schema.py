from django.contrib.auth import get_user_model
from django.test import SimpleTestCase
from django.utils import timezone
from drf_spectacular.generators import SchemaGenerator
from rest_framework.test import APITestCase

from api.models import AirExposureLog, Exposure
from api.serializers import AirExposureLogSerializer, SimpleExposureSerializer


User = get_user_model()


class WaterExposureSerializerContractTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="water-exposure-schema@example.com",
            password="testpass123",
        )

    def test_exposure_risk_map_validates_without_changing_runtime_values(self):
        exposure = Exposure.objects.create(
            user=self.user,
            exposure_level=0.62,
            risks={"pm25": "moderate", "uvi": "low"},
        )

        payload = SimpleExposureSerializer(exposure).data

        self.assertEqual(
            payload["risks"],
            {"pm25": "moderate", "uvi": "low"},
        )
        serializer = SimpleExposureSerializer(data=payload)
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_partial_environment_payload_validates_with_nullable_values(self):
        log = AirExposureLog.objects.create(
            user=self.user,
            timestamp=timezone.now(),
            latitude=5.6037,
            longitude=-0.1870,
            h3_cell=None,
            pm25=None,
            temperature=None,
            activity_level=None,
        )

        payload = AirExposureLogSerializer(log).data

        self.assertIsNone(payload["h3_cell"])
        self.assertIsNone(payload["pm25"])
        self.assertIsNone(payload["temperature"])
        self.assertIsNone(payload["activity_level"])
        serializer = AirExposureLogSerializer(data=payload)
        self.assertTrue(serializer.is_valid(), serializer.errors)


class WaterExposureOpenAPIContractTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.schema = SchemaGenerator().get_schema(request=None, public=True)

    @classmethod
    def _resolve(cls, value):
        if "$ref" in value:
            name = value["$ref"].rsplit("/", 1)[-1]
            return cls.schema["components"]["schemas"][name]
        if "allOf" in value and len(value["allOf"]) == 1:
            return cls._resolve(value["allOf"][0])
        return value

    def test_summary_exposure_risks_are_typed_string_maps(self):
        operation = self.schema["paths"]["/api/summary/"]["get"]
        summary = self._resolve(
            operation["responses"]["200"]["content"]["application/json"][
                "schema"
            ]
        )

        for field_name in ("mom_exposure", "baby_exposure"):
            exposure = self._resolve(summary["properties"][field_name])
            risks = exposure["properties"]["risks"]
            self.assertEqual(risks["type"], "object")
            self.assertEqual(
                risks["additionalProperties"],
                {"type": "string"},
            )

    def test_water_goal_and_daily_log_have_stable_value_and_unit_types(self):
        catalog_operation = self.schema["paths"]["/api/wellbeing/"]["get"]
        catalog = self._resolve(
            catalog_operation["responses"]["200"]["content"][
                "application/json"
            ]["schema"]
        )
        water_goal = self._resolve(catalog["properties"]["water_goal"])
        self.assertEqual(water_goal["properties"]["value"]["type"], "number")
        self.assertTrue(water_goal["properties"]["value"]["nullable"])
        self.assertEqual(water_goal["properties"]["unit"]["type"], "string")

        log_operation = self.schema["paths"]["/api/wellbeing/log/"]["get"]
        log_response = self._resolve(
            log_operation["responses"]["200"]["content"]["application/json"][
                "schema"
            ]
        )
        self.assertEqual(
            log_response["properties"]["water_amount"]["type"],
            "number",
        )
        self.assertEqual(
            log_response["properties"]["water_unit"]["type"],
            "string",
        )

        empty_example = log_operation["responses"]["200"]["content"][
            "application/json"
        ]["examples"]["EmptyLogExample"]["value"]
        self.assertEqual(empty_example["water_amount"], 0)
        self.assertEqual(empty_example["moods"], [])
        self.assertEqual(empty_example["feelings"], [])

        error = self._resolve(
            log_operation["responses"]["400"]["content"]["application/json"][
                "schema"
            ]
        )
        self.assertEqual(error["properties"]["detail"]["type"], "string")

    def test_environment_schema_types_nullable_partial_and_no_data_contracts(self):
        operation = self.schema["paths"]["/api/air-exposure/"]["get"]
        environment = self._resolve(
            operation["responses"]["200"]["content"]["application/json"][
                "schema"
            ]
        )
        properties = environment["properties"]

        self.assertEqual(properties["timestamp"]["format"], "date-time")
        self.assertEqual(properties["latitude"]["type"], "number")
        self.assertEqual(properties["indoor"]["type"], "boolean")
        for field_name in (
            "h3_cell",
            "pm25",
            "pm10",
            "temperature",
            "uvi",
            "activity_level",
        ):
            self.assertTrue(properties[field_name]["nullable"])

        self.assertEqual(
            operation["responses"]["204"],
            {"description": "No air exposure data available."},
        )
