from django.contrib.admin.sites import AdminSite
from django.test import SimpleTestCase

from api.admin import AirExposureLogAdmin, MovementAdmin
from api.models import AirExposureLog, Movement


class MovementAdminPrivacyTests(SimpleTestCase):
    def setUp(self):
        self.model_admin = MovementAdmin(Movement, AdminSite())

    def test_movement_admin_does_not_expose_raw_coordinates(self):
        list_display = self.model_admin.get_list_display(request=None)
        excluded_fields = self.model_admin.get_exclude(request=None, obj=None)

        self.assertNotIn("latitude", list_display)
        self.assertNotIn("longitude", list_display)
        self.assertIn("latitude", excluded_fields)
        self.assertIn("longitude", excluded_fields)
        self.assertIn("coordinates_encrypted", excluded_fields)

    def test_air_exposure_admin_does_not_expose_raw_coordinates(self):
        model_admin = AirExposureLogAdmin(AirExposureLog, AdminSite())
        list_display = model_admin.get_list_display(request=None)
        excluded_fields = model_admin.get_exclude(request=None, obj=None)

        self.assertNotIn("latitude", list_display)
        self.assertNotIn("longitude", list_display)
        self.assertIn("latitude", excluded_fields)
        self.assertIn("longitude", excluded_fields)
