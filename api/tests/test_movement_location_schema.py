from django.db import models
from django.test import SimpleTestCase

from api.models import AirExposureLog, Movement


class MovementLocationSchemaTests(SimpleTestCase):
    def test_movement_security_fields_are_nullable_during_rollout(self):
        expected_fields = {
            "h3_cell": models.CharField,
            "coordinates_encrypted": models.BinaryField,
            "coordinates_key_version": models.PositiveSmallIntegerField,
            "coordinates_purged_at": models.DateTimeField,
        }

        for field_name, field_type in expected_fields.items():
            with self.subTest(field=field_name):
                field = Movement._meta.get_field(field_name)
                self.assertIsInstance(field, field_type)
                self.assertTrue(field.null)
                self.assertTrue(field.blank)
                self.assertFalse(field.editable)

        self.assertEqual(Movement._meta.get_field("h3_cell").max_length, 15)

    def test_movement_query_indexes_are_declared(self):
        indexes = {
            index.name: tuple(index.fields) for index in Movement._meta.indexes
        }

        self.assertEqual(
            indexes["movement_user_ts_idx"],
            ("user", "timestamp"),
        )
        self.assertEqual(
            indexes["movement_user_h3_ts_idx"],
            ("user", "h3_cell", "timestamp"),
        )

    def test_air_exposure_h3_field_and_index_are_declared(self):
        field = AirExposureLog._meta.get_field("h3_cell")

        self.assertIsInstance(field, models.CharField)
        self.assertEqual(field.max_length, 15)
        self.assertTrue(field.null)
        self.assertTrue(field.blank)
        self.assertFalse(field.editable)

        indexes = {
            index.name: tuple(index.fields)
            for index in AirExposureLog._meta.indexes
        }
        self.assertEqual(
            indexes["airexp_user_h3_ts_idx"],
            ("user", "h3_cell", "timestamp"),
        )
