from django.test import SimpleTestCase, override_settings

from api.services.h3_grid import (
    InvalidCoordinatesError,
    InvalidH3CellError,
    cell_to_center,
    cell_to_parent,
    configured_resolution,
    latlng_to_cell,
    validate_cell,
    validate_coordinates,
)


@override_settings(MOVEMENT_H3_RESOLUTION=8)
class H3GridTests(SimpleTestCase):
    VILNIUS_LATITUDE = 54.6872
    VILNIUS_LONGITUDE = 25.2797
    VILNIUS_H3_RESOLUTION_8 = "881f4030c7fffff"

    def test_latlng_to_cell_uses_configured_resolution(self):
        cell = latlng_to_cell(self.VILNIUS_LATITUDE, self.VILNIUS_LONGITUDE)

        self.assertEqual(cell, self.VILNIUS_H3_RESOLUTION_8)
        self.assertEqual(configured_resolution(), 8)
        self.assertEqual(validate_cell(cell, expected_resolution=8), cell)

    def test_coordinate_order_is_latitude_then_longitude(self):
        correct = latlng_to_cell(self.VILNIUS_LATITUDE, self.VILNIUS_LONGITUDE)
        swapped = latlng_to_cell(self.VILNIUS_LONGITUDE, self.VILNIUS_LATITUDE)

        self.assertEqual(correct, self.VILNIUS_H3_RESOLUTION_8)
        self.assertNotEqual(swapped, correct)

    def test_cell_to_center_returns_coordinates_inside_vilnius_cell(self):
        latitude, longitude = cell_to_center(self.VILNIUS_H3_RESOLUTION_8)

        self.assertAlmostEqual(latitude, 54.68796922159753)
        self.assertAlmostEqual(longitude, 25.281043518584067)

    def test_cell_to_parent_returns_requested_resolution(self):
        parent = cell_to_parent(self.VILNIUS_H3_RESOLUTION_8, 7)

        self.assertEqual(parent, "871f4030cffffff")
        self.assertEqual(validate_cell(parent, expected_resolution=7), parent)

    def test_validate_coordinates_normalizes_numeric_strings(self):
        self.assertEqual(validate_coordinates("54.6872", "25.2797"), (54.6872, 25.2797))

    def test_validate_coordinates_rejects_invalid_values(self):
        invalid_pairs = [
            (91, 25),
            (-91, 25),
            (54, 181),
            (54, -181),
            (float("nan"), 25),
            (54, float("inf")),
            (True, 25),
            (None, 25),
        ]

        for latitude, longitude in invalid_pairs:
            with self.subTest(latitude=latitude, longitude=longitude):
                with self.assertRaises(InvalidCoordinatesError):
                    validate_coordinates(latitude, longitude)

    def test_validate_cell_rejects_invalid_cell(self):
        with self.assertRaises(InvalidH3CellError):
            validate_cell("not-an-h3-cell")

    def test_validate_cell_rejects_unexpected_resolution(self):
        with self.assertRaises(InvalidH3CellError):
            validate_cell(self.VILNIUS_H3_RESOLUTION_8, expected_resolution=7)

    @override_settings(MOVEMENT_H3_RESOLUTION=16)
    def test_configured_resolution_rejects_out_of_range_value(self):
        with self.assertRaises(InvalidH3CellError):
            configured_resolution()

    def test_parent_resolution_cannot_be_finer_than_cell(self):
        with self.assertRaises(InvalidH3CellError):
            cell_to_parent(self.VILNIUS_H3_RESOLUTION_8, 9)
