import base64
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.utils import timezone

from api.models import Movement, User
from api.services.coordinate_encryption import (
    decrypt_coordinates,
    encrypt_coordinates,
)
from api.services.h3_grid import latlng_to_cell


KEY_VERSION_1 = base64.b64encode(b"A" * 32).decode("ascii")


@override_settings(
    MOVEMENT_H3_RESOLUTION=8,
    MOVEMENT_COORDINATE_ACTIVE_KEY_VERSION=1,
    MOVEMENT_COORDINATE_KEYS={1: KEY_VERSION_1},
)
class BackfillMovementLocationsTests(TestCase):
    LATITUDE = 54.6872
    LONGITUDE = 25.2797

    def setUp(self):
        self.user = User.objects.create_user(
            email="backfill@test.local",
            password="pass1234",
        )

    def create_movement(self, **overrides):
        values = {
            "user": self.user,
            "latitude": self.LATITUDE,
            "longitude": self.LONGITUDE,
            "timestamp": timezone.now(),
        }
        values.update(overrides)
        return Movement.objects.create(**values)

    def test_backfills_existing_movement(self):
        movement = self.create_movement()
        stdout = StringIO()

        call_command(
            "backfill_movement_locations",
            batch_size=1,
            stdout=stdout,
        )

        movement.refresh_from_db()
        self.assertEqual(
            movement.h3_cell,
            latlng_to_cell(self.LATITUDE, self.LONGITUDE),
        )
        self.assertEqual(movement.coordinates_key_version, 1)
        self.assertIsNotNone(movement.coordinates_encrypted)
        decrypted = decrypt_coordinates(
            movement.coordinates_encrypted,
            movement.coordinates_key_version,
        )
        self.assertEqual(decrypted.latitude, self.LATITUDE)
        self.assertEqual(decrypted.longitude, self.LONGITUDE)
        self.assertIn("Backfilled 1 movement(s).", stdout.getvalue())

    def test_second_run_is_idempotent(self):
        movement = self.create_movement()
        call_command("backfill_movement_locations", verbosity=0)
        movement.refresh_from_db()
        original_ciphertext = bytes(movement.coordinates_encrypted)
        stdout = StringIO()

        call_command(
            "backfill_movement_locations",
            stdout=stdout,
        )

        movement.refresh_from_db()
        self.assertEqual(
            bytes(movement.coordinates_encrypted),
            original_ciphertext,
        )
        self.assertIn("Backfilled 0 movement(s).", stdout.getvalue())

    def test_preserves_existing_location_representations(self):
        expected_h3_cell = latlng_to_cell(self.LATITUDE, self.LONGITUDE)
        encrypted = encrypt_coordinates(self.LATITUDE, self.LONGITUDE)
        h3_only = self.create_movement(h3_cell=expected_h3_cell)
        encrypted_only = self.create_movement(
            coordinates_encrypted=encrypted.ciphertext,
            coordinates_key_version=encrypted.key_version,
        )

        call_command("backfill_movement_locations", batch_size=1, verbosity=0)

        h3_only.refresh_from_db()
        encrypted_only.refresh_from_db()
        self.assertEqual(h3_only.h3_cell, expected_h3_cell)
        self.assertIsNotNone(h3_only.coordinates_encrypted)
        self.assertEqual(
            encrypted_only.h3_cell,
            expected_h3_cell,
        )
        self.assertEqual(
            bytes(encrypted_only.coordinates_encrypted),
            encrypted.ciphertext,
        )
        self.assertEqual(
            encrypted_only.coordinates_key_version,
            encrypted.key_version,
        )

    def test_rejects_non_positive_batch_size(self):
        with self.assertRaisesMessage(
            CommandError,
            "--batch-size must be a positive integer",
        ):
            call_command("backfill_movement_locations", batch_size=0)
