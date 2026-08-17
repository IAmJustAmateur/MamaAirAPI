import base64

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from api.models import Movement
from api.services.coordinate_encryption import decrypt_coordinates
from api.services.h3_grid import latlng_to_cell
from demo_interface.utils import generate_plausible_movements_24h


KEY_VERSION_1 = base64.b64encode(b"A" * 32).decode("ascii")


@override_settings(
    MOVEMENT_H3_RESOLUTION=8,
    MOVEMENT_COORDINATE_ACTIVE_KEY_VERSION=1,
    MOVEMENT_COORDINATE_KEYS={1: KEY_VERSION_1},
)
class GeneratedMovementSecurityTests(TestCase):
    def test_generated_movements_include_h3_and_encrypted_coordinates(self):
        user = get_user_model().objects.create_user(
            email="generated-movements@test.local",
            password="pass1234",
        )

        result = generate_plausible_movements_24h(user, step_minutes=60)

        self.assertGreater(result["created"], 0)
        movement = Movement.objects.filter(user=user).first()
        self.assertIsNotNone(movement)
        self.assertEqual(
            movement.h3_cell,
            latlng_to_cell(movement.latitude, movement.longitude),
        )
        decrypted = decrypt_coordinates(
            movement.coordinates_encrypted,
            movement.coordinates_key_version,
        )
        self.assertAlmostEqual(decrypted.latitude, movement.latitude, places=7)
        self.assertAlmostEqual(decrypted.longitude, movement.longitude, places=7)

