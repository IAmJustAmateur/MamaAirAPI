from __future__ import annotations

from math import isfinite

import h3
from django.conf import settings


class InvalidCoordinatesError(ValueError):
    """Raised when latitude or longitude is invalid."""


class InvalidH3CellError(ValueError):
    """Raised when an H3 cell is invalid or has an unexpected resolution."""


def _coerce_coordinate(value: float, name: str) -> float:
    if isinstance(value, bool):
        raise InvalidCoordinatesError(f"{name} must be a finite number")

    try:
        coordinate = float(value)
    except (TypeError, ValueError) as exc:
        raise InvalidCoordinatesError(f"{name} must be a finite number") from exc

    if not isfinite(coordinate):
        raise InvalidCoordinatesError(f"{name} must be a finite number")
    return coordinate


def validate_coordinates(latitude: float, longitude: float) -> tuple[float, float]:
    """Validate and normalize a WGS84 latitude/longitude pair."""
    lat = _coerce_coordinate(latitude, "latitude")
    lon = _coerce_coordinate(longitude, "longitude")

    if not -90.0 <= lat <= 90.0:
        raise InvalidCoordinatesError("latitude must be between -90 and 90")
    if not -180.0 <= lon <= 180.0:
        raise InvalidCoordinatesError("longitude must be between -180 and 180")

    return lat, lon


def configured_resolution() -> int:
    """Return the configured canonical movement H3 resolution."""
    try:
        resolution = int(getattr(settings, "MOVEMENT_H3_RESOLUTION", 8))
    except (TypeError, ValueError) as exc:
        raise InvalidH3CellError("MOVEMENT_H3_RESOLUTION must be an integer") from exc

    if not 0 <= resolution <= 15:
        raise InvalidH3CellError("MOVEMENT_H3_RESOLUTION must be between 0 and 15")
    return resolution


def validate_cell(h3_cell: str, *, expected_resolution: int | None = None) -> str:
    """Validate an H3 cell and optionally enforce its resolution."""
    if not isinstance(h3_cell, str) or not h3.is_valid_cell(h3_cell):
        raise InvalidH3CellError("invalid H3 cell")

    if expected_resolution is not None:
        try:
            expected = int(expected_resolution)
        except (TypeError, ValueError) as exc:
            raise InvalidH3CellError("expected resolution must be an integer") from exc
        if not 0 <= expected <= 15:
            raise InvalidH3CellError("expected resolution must be between 0 and 15")
        if h3.get_resolution(h3_cell) != expected:
            raise InvalidH3CellError(
                f"H3 cell resolution must be {expected}, "
                f"got {h3.get_resolution(h3_cell)}"
            )

    return h3_cell


def latlng_to_cell(
    latitude: float,
    longitude: float,
    *,
    resolution: int | None = None,
) -> str:
    """Return the H3 cell containing the supplied coordinates."""
    lat, lon = validate_coordinates(latitude, longitude)
    target_resolution = configured_resolution() if resolution is None else int(resolution)

    if not 0 <= target_resolution <= 15:
        raise InvalidH3CellError("resolution must be between 0 and 15")

    return h3.latlng_to_cell(lat, lon, target_resolution)


def cell_to_center(h3_cell: str) -> tuple[float, float]:
    """Return the latitude/longitude center of an H3 cell."""
    cell = validate_cell(h3_cell)
    latitude, longitude = h3.cell_to_latlng(cell)
    return float(latitude), float(longitude)


def cell_to_parent(h3_cell: str, resolution: int) -> str:
    """Return a parent of an H3 cell at a coarser resolution."""
    cell = validate_cell(h3_cell)
    current_resolution = h3.get_resolution(cell)

    try:
        parent_resolution = int(resolution)
    except (TypeError, ValueError) as exc:
        raise InvalidH3CellError("parent resolution must be an integer") from exc

    if not 0 <= parent_resolution <= current_resolution:
        raise InvalidH3CellError(
            "parent resolution must be between 0 and the cell resolution"
        )

    return h3.cell_to_parent(cell, parent_resolution)
