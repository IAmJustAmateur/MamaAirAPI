from rest_framework.test import APITestCase
from django.contrib.auth import get_user_model
from api.models import MommySymptom, UserMommySymptoms, UserLifeStyle

User = get_user_model()


class UserMommySymptomsSelectionTests(APITestCase):
    """
    Новый контракт:
    1) Чек-лист (read-only): GET /api/symptoms/mommy/checklist/
       -> {"symptoms": [{"id": int, "name": str}, ...]}
    2) Сохранение выбора пользователя (без CRUD по записям):
       - POST /api/symptoms/mommy/selection/ {"symptom_ids": [int, ...]}
         Заменяет весь набор выбранных симптомов пользователя на переданный список (replace-all).
       - GET  /api/symptoms/mommy/selection/ -> {"symptom_ids": [int, ...]}
    """

    BASE = "/api/"

    def setUp(self):
        # user + auth
        self.email = "mom1@example.com"
        self.password = "Testpass123!"
        self.user = User.objects.create_user(
            email=self.email,
            password=self.password,
            name="Mommy",
            date_of_birth="1995-08-02",
            height=170,
            weight_pre_pregnancy=60,
            is_first_pregnancy=True,
            race="caucasian",
            week_of_pregnancy=3,
        )
        UserLifeStyle.objects.create(
            user=self.user,
            cooking_method="charcoal",
            diet_type="carnivore",
            work_type="desk",
            average_sleep_hours=7,
            activity_duration_minutes=120,
        )
        resp = self.client.post(
            self.BASE + "auth/token/",
            {"email": self.email, "password": self.password},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.data)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.data['access']}")

        # dictionary symptoms
        self.s1 = MommySymptom.objects.get_or_create(name="Headache")[0]
        self.s2 = MommySymptom.objects.get_or_create(name="Nausea")[0]
        self.s3 = MommySymptom.objects.get_or_create(name="Vomiting")[0]

        self.checklist_url = self.BASE + "symptoms/mommy/checklist/"
        self.selection_url = self.BASE + "symptoms/mommy/selection/"

    # ---------- Checklist (read-only) ----------
    def test_checklist_returns_objects_with_id_and_name(self):
        resp = self.client.get(self.checklist_url)
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertIn("symptoms", resp.data)
        self.assertIsInstance(resp.data["symptoms"], list)
        if resp.data["symptoms"]:
            first = resp.data["symptoms"][0]
            self.assertIn("id", first)
            self.assertIn("name", first)
            self.assertIsInstance(first["name"], str)
            # id может быть int (или None, если БД-справочник не содержит такого имени)
            if first["id"] is not None:
                self.assertIsInstance(first["id"], int)

    # ---------- Selection (replace-all) ---------- (replace-all) ----------
    def test_selection_roundtrip(self):
        # Save selection [s1, s3]
        payload = {"symptom_ids": [self.s1.id, self.s3.id]}
        r = self.client.post(self.selection_url, payload, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(
            sorted(r.data.get("symptom_ids", [])), sorted(payload["symptom_ids"])
        )

        # DB: exactly two records for current user
        ids_in_db = list(
            UserMommySymptoms.objects.filter(user=self.user).values_list(
                "symptom_id", flat=True
            )
        )
        self.assertEqual(sorted(ids_in_db), sorted(payload["symptom_ids"]))

        # GET selection -> same set
        r = self.client.get(self.selection_url)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(
            sorted(r.data.get("symptom_ids", [])), sorted(payload["symptom_ids"])
        )

    def test_selection_overwrites_previous(self):
        # initial selection [s1]
        r1 = self.client.post(
            self.selection_url, {"symptom_ids": [self.s1.id]}, format="json"
        )
        self.assertEqual(r1.status_code, 200, r1.data)
        # overwrite with [s2]
        r2 = self.client.post(
            self.selection_url, {"symptom_ids": [self.s2.id]}, format="json"
        )
        self.assertEqual(r2.status_code, 200, r2.data)
        self.assertEqual(r2.data.get("symptom_ids"), [self.s2.id])

        ids_in_db = list(
            UserMommySymptoms.objects.filter(user=self.user).values_list(
                "symptom_id", flat=True
            )
        )
        self.assertEqual(ids_in_db, [self.s2.id])

    def test_selection_rejects_unknown_ids(self):
        # unknown ID 9999
        r = self.client.post(
            self.selection_url, {"symptom_ids": [self.s1.id, 9999]}, format="json"
        )
        self.assertIn(r.status_code, (400, 422))
