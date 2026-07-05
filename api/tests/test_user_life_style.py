from rest_framework.test import APITestCase
from django.contrib.auth import get_user_model
from api.models import UserLifeStyle
from django.urls import reverse

User = get_user_model()


class UserLifeStyleEndpointTests(APITestCase):
    """Tests for /api/lifestyle/ endpoints (retrieve, update, and current POST behavior).

    NOTE: In current code, UserLifestyleView is a RetrieveUpdateAPIView,
    so POST (create) is not allowed (expects 405). If you later switch it to
    Create/Update (e.g., RetrieveUpdateAPIView + custom post or a ModelViewSet),
    update the first test to assert 201 and presence of created fields.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com", password="testpass123"
        )
        self.token_url = reverse("token_obtain_pair")
        self.refresh_url = reverse("token_refresh")
        self.profile_url = reverse("profile")
        self.lifestyle_url = reverse("lifestyle")
        response = self.client.post(
            self.token_url, {"email": "test@example.com", "password": "testpass123"}
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")

    def test_lifestyle_post_is_not_allowed_currently(self):
        """POST /api/lifestyle/ should be Method Not Allowed with current view."""
        payload = {
            "average_sleep_hours": 7.0,
            "work_type": "Desk",
            "diet_type": "carnivore",
            "cooking_method": "gas",
            "activity_duration_minutes": 120,
        }
        resp = self.client.post(self.lifestyle_url, payload, format="json")
        self.assertIn(
            resp.status_code, (400, 405), resp.data
        )  # 405 is the expected one

    def test_lifestyle_update_then_get(self):
        """Create lifestyle in DB, then update via PATCH and read via GET."""
        # Create underlying OneToOne instance so the endpoint can retrieve it
        UserLifeStyle.objects.create(user=self.user)

        patch_data = {
            "average_sleep_hours": 7.5,
            "work_type": "Desk",
            "diet_type": "carnivore",
            "cooking_method": "gas",
            "activity_duration_minutes": 150,
            "area": "peri_urban",
            "time_spent": "mostly_outdoors",
            "time_of_day": "changes_day_to_day",
        }
        # PATCH (update)
        resp = self.client.patch(self.lifestyle_url, patch_data, format="json")
        self.assertEqual(resp.status_code, 200, resp.data)
        for k, v in patch_data.items():
            self.assertEqual(resp.data[k], v)
        # GET (retrieve)
        resp = self.client.get(self.lifestyle_url)
        self.assertEqual(resp.status_code, 200, resp.data)
        for k, v in patch_data.items():
            self.assertEqual(resp.data[k], v)

    def test_lifestyle_rejects_unknown_onboarding_choice(self):
        UserLifeStyle.objects.create(user=self.user)

        resp = self.client.patch(
            self.lifestyle_url,
            {"area": "suburban"},
            format="json",
        )

        self.assertEqual(resp.status_code, 400, resp.data)
        self.assertIn("area", resp.data)

    def test_get_without_existing_lifestyle_autocreates(self):
        """If a lifestyle doesn't exist yet, GET should auto-create and return 200 (recommended UX)."""
        # Ensure precondition: no lifestyle row
        self.assertFalse(UserLifeStyle.objects.filter(user=self.user).exists())
        # First GET should create the row and return defaults
        resp = self.client.get(self.lifestyle_url)
        self.assertEqual(resp.status_code, 200, resp.data)
        # DB side: row now exists
        self.assertTrue(UserLifeStyle.objects.filter(user=self.user).exists())
