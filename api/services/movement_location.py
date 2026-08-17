from __future__ import annotations

from dataclasses import dataclass

from api.services.coordinate_encryption import encrypt_coordinates
from api.services.h3_grid import latlng_to_cell, validate_coordinates


@dataclass(frozen=True)
class PreparedMovementLocation:
    latitude: float
    longitude: float
    h3_cell: str
    coordinates_encrypted: bytes
    coordinates_key_version: int


def prepare_movement_location(
    latitude: float,
    longitude: float,
) -> PreparedMovementLocation:
    """Validate and prepare all location representations for one Movement."""
    lat, lon = validate_coordinates(latitude, longitude)
    encrypted = encrypt_coordinates(lat, lon)

    return PreparedMovementLocation(
        latitude=lat,
        longitude=lon,
        h3_cell=latlng_to_cell(lat, lon),
        coordinates_encrypted=encrypted.ciphertext,
        coordinates_key_version=encrypted.key_version,
    )
