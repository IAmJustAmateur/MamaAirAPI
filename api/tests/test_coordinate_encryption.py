import base64

from django.test import SimpleTestCase, override_settings

from api.services.coordinate_encryption import (
    CoordinateDecryptionError,
    CoordinateEncryptionConfigurationError,
    decrypt_coordinates,
    encrypt_coordinates,
)
from api.services.h3_grid import InvalidCoordinatesError


KEY_VERSION_1 = base64.b64encode(b"A" * 32).decode("ascii")
KEY_VERSION_2 = base64.b64encode(b"B" * 32).decode("ascii")


@override_settings(
    MOVEMENT_COORDINATE_ACTIVE_KEY_VERSION=1,
    MOVEMENT_COORDINATE_KEYS={
        1: KEY_VERSION_1,
        2: KEY_VERSION_2,
    },
)
class CoordinateEncryptionTests(SimpleTestCase):
    LATITUDE = 54.6872
    LONGITUDE = 25.2797

    def test_encrypt_decrypt_round_trip(self):
        encrypted = encrypt_coordinates(self.LATITUDE, self.LONGITUDE)
        decrypted = decrypt_coordinates(
            encrypted.ciphertext,
            encrypted.key_version,
        )

        self.assertEqual(encrypted.key_version, 1)
        self.assertEqual(decrypted.latitude, self.LATITUDE)
        self.assertEqual(decrypted.longitude, self.LONGITUDE)

    def test_same_coordinates_produce_different_ciphertexts(self):
        first = encrypt_coordinates(self.LATITUDE, self.LONGITUDE)
        second = encrypt_coordinates(self.LATITUDE, self.LONGITUDE)

        self.assertNotEqual(first.ciphertext, second.ciphertext)
        self.assertEqual(
            decrypt_coordinates(first.ciphertext, first.key_version),
            decrypt_coordinates(second.ciphertext, second.key_version),
        )

    @override_settings(MOVEMENT_COORDINATE_ACTIVE_KEY_VERSION=2)
    def test_active_key_version_is_used_for_new_ciphertext(self):
        encrypted = encrypt_coordinates(self.LATITUDE, self.LONGITUDE)

        self.assertEqual(encrypted.key_version, 2)
        self.assertEqual(
            decrypt_coordinates(encrypted.ciphertext, 2).latitude,
            self.LATITUDE,
        )

    def test_old_and_new_key_versions_can_be_decrypted_during_rotation(self):
        old = encrypt_coordinates(
            self.LATITUDE,
            self.LONGITUDE,
            key_version=1,
        )
        new = encrypt_coordinates(
            self.LATITUDE,
            self.LONGITUDE,
            key_version=2,
        )

        self.assertEqual(
            decrypt_coordinates(old.ciphertext, old.key_version).longitude,
            self.LONGITUDE,
        )
        self.assertEqual(
            decrypt_coordinates(new.ciphertext, new.key_version).longitude,
            self.LONGITUDE,
        )

    def test_tampered_ciphertext_is_rejected(self):
        encrypted = encrypt_coordinates(self.LATITUDE, self.LONGITUDE)
        tampered = bytearray(encrypted.ciphertext)
        tampered[-1] ^= 1

        with self.assertRaises(CoordinateDecryptionError):
            decrypt_coordinates(bytes(tampered), encrypted.key_version)

    def test_wrong_key_version_is_rejected(self):
        encrypted = encrypt_coordinates(
            self.LATITUDE,
            self.LONGITUDE,
            key_version=1,
        )

        with self.assertRaises(CoordinateDecryptionError):
            decrypt_coordinates(encrypted.ciphertext, 2)

    def test_memoryview_ciphertext_can_be_decrypted(self):
        encrypted = encrypt_coordinates(self.LATITUDE, self.LONGITUDE)

        decrypted = decrypt_coordinates(
            memoryview(encrypted.ciphertext),
            encrypted.key_version,
        )

        self.assertEqual(decrypted.latitude, self.LATITUDE)
        self.assertEqual(decrypted.longitude, self.LONGITUDE)

    def test_invalid_coordinates_are_rejected_before_encryption(self):
        with self.assertRaises(InvalidCoordinatesError):
            encrypt_coordinates(91, self.LONGITUDE)

    @override_settings(MOVEMENT_COORDINATE_KEYS={})
    def test_missing_key_is_reported_as_configuration_error(self):
        with self.assertRaises(CoordinateEncryptionConfigurationError):
            encrypt_coordinates(self.LATITUDE, self.LONGITUDE)

    @override_settings(MOVEMENT_COORDINATE_KEYS={1: "not-base64"})
    def test_invalid_base64_key_is_reported_as_configuration_error(self):
        with self.assertRaises(CoordinateEncryptionConfigurationError):
            encrypt_coordinates(self.LATITUDE, self.LONGITUDE)

    @override_settings(
        MOVEMENT_COORDINATE_KEYS={
            1: base64.b64encode(b"too-short").decode("ascii"),
        }
    )
    def test_wrong_key_length_is_reported_as_configuration_error(self):
        with self.assertRaises(CoordinateEncryptionConfigurationError):
            encrypt_coordinates(self.LATITUDE, self.LONGITUDE)

    def test_truncated_ciphertext_is_rejected(self):
        with self.assertRaises(CoordinateDecryptionError):
            decrypt_coordinates(b"short", 1)
