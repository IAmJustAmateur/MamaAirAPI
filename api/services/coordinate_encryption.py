from __future__ import annotations

import base64
import json
import os
from collections.abc import Mapping
from dataclasses import dataclass

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.conf import settings

from api.services.h3_grid import validate_coordinates


_PAYLOAD_FORMAT_VERSION = 1
_NONCE_SIZE = 12
_MINIMUM_CIPHERTEXT_SIZE = 16
_AAD_PREFIX = b"mamaair:movement-coordinates:"


class CoordinateEncryptionError(Exception):
    """Base exception for coordinate encryption failures."""


class CoordinateEncryptionConfigurationError(CoordinateEncryptionError):
    """Raised when coordinate encryption keys are not configured correctly."""


class CoordinateDecryptionError(CoordinateEncryptionError):
    """Raised when encrypted coordinates cannot be authenticated or decoded."""


@dataclass(frozen=True)
class Coordinates:
    latitude: float
    longitude: float


@dataclass(frozen=True)
class EncryptedCoordinates:
    ciphertext: bytes
    key_version: int


def _normalize_key_version(value: int) -> int:
    try:
        key_version = int(value)
    except (TypeError, ValueError) as exc:
        raise CoordinateEncryptionConfigurationError(
            "coordinate encryption key version must be an integer"
        ) from exc

    if key_version < 1:
        raise CoordinateEncryptionConfigurationError(
            "coordinate encryption key version must be positive"
        )
    return key_version


def _active_key_version() -> int:
    return _normalize_key_version(
        getattr(settings, "MOVEMENT_COORDINATE_ACTIVE_KEY_VERSION", 1)
    )


def _decode_key(key_version: int) -> bytes:
    configured_keys = getattr(settings, "MOVEMENT_COORDINATE_KEYS", {})
    if not isinstance(configured_keys, Mapping):
        raise CoordinateEncryptionConfigurationError(
            "MOVEMENT_COORDINATE_KEYS must be a mapping"
        )

    encoded_key = configured_keys.get(key_version)
    if encoded_key is None:
        encoded_key = configured_keys.get(str(key_version))
    if not isinstance(encoded_key, str) or not encoded_key:
        raise CoordinateEncryptionConfigurationError(
            f"coordinate encryption key version {key_version} is not configured"
        )

    try:
        key = base64.b64decode(encoded_key, validate=True)
    except (ValueError, TypeError) as exc:
        raise CoordinateEncryptionConfigurationError(
            f"coordinate encryption key version {key_version} is not valid base64"
        ) from exc

    if len(key) != 32:
        raise CoordinateEncryptionConfigurationError(
            f"coordinate encryption key version {key_version} must decode to 32 bytes"
        )
    return key


def _associated_data(key_version: int) -> bytes:
    return _AAD_PREFIX + str(key_version).encode("ascii")


def encrypt_coordinates(
    latitude: float,
    longitude: float,
    *,
    key_version: int | None = None,
) -> EncryptedCoordinates:
    """Encrypt a validated latitude/longitude pair using AES-256-GCM."""
    lat, lon = validate_coordinates(latitude, longitude)
    version = (
        _active_key_version()
        if key_version is None
        else _normalize_key_version(key_version)
    )
    key = _decode_key(version)

    plaintext = json.dumps(
        {"latitude": lat, "longitude": lon},
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    nonce = os.urandom(_NONCE_SIZE)
    encrypted_payload = AESGCM(key).encrypt(
        nonce,
        plaintext,
        _associated_data(version),
    )

    packed_payload = bytes([_PAYLOAD_FORMAT_VERSION]) + nonce + encrypted_payload
    return EncryptedCoordinates(ciphertext=packed_payload, key_version=version)


def decrypt_coordinates(ciphertext: bytes, key_version: int) -> Coordinates:
    """Authenticate and decrypt a packed coordinate payload."""
    version = _normalize_key_version(key_version)

    try:
        packed_payload = bytes(ciphertext)
    except (TypeError, ValueError) as exc:
        raise CoordinateDecryptionError("coordinate ciphertext must be bytes") from exc

    minimum_size = 1 + _NONCE_SIZE + _MINIMUM_CIPHERTEXT_SIZE
    if len(packed_payload) < minimum_size:
        raise CoordinateDecryptionError("coordinate ciphertext is truncated")
    if packed_payload[0] != _PAYLOAD_FORMAT_VERSION:
        raise CoordinateDecryptionError("unsupported coordinate ciphertext format")

    nonce = packed_payload[1 : 1 + _NONCE_SIZE]
    encrypted_payload = packed_payload[1 + _NONCE_SIZE :]
    key = _decode_key(version)

    try:
        plaintext = AESGCM(key).decrypt(
            nonce,
            encrypted_payload,
            _associated_data(version),
        )
    except InvalidTag as exc:
        raise CoordinateDecryptionError(
            "coordinate ciphertext authentication failed"
        ) from exc

    try:
        payload = json.loads(plaintext.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("coordinate payload must be an object")
        latitude, longitude = validate_coordinates(
            payload["latitude"],
            payload["longitude"],
        )
    except (KeyError, TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CoordinateDecryptionError("coordinate payload is invalid") from exc

    return Coordinates(latitude=latitude, longitude=longitude)
