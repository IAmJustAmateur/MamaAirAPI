from rest_framework.test import APITestCase
from django.contrib.auth import get_user_model
from api.models import MommySymptom, UserMommySymptoms, UserLifeStyle
from .utils import create_defaults
from django.urls import reverse

User = get_user_model()


class UserSymptomsSelectionTests(APITestCase):
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
        defaults = create_defaults()
        self.email = defaults["user"].email
        self.password = defaults["password"]

        resp = self.client.post(
            self.BASE + "auth/token/",
            {"email": self.email, "password": self.password},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.data)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.data['access']}")

        # dictionary symptoms
        self.ms1 = defaults["mommy_symptoms"][0]
        self.ms2 = defaults["mommy_symptoms"][1]
        self.ms3 = defaults["mommy_symptoms"][2]

        self.bs1 = defaults["baby_symptoms"][0]
        self.bs2 = defaults["baby_symptoms"][1]
        self.bs3 = defaults["baby_symptoms"][2]

        self.mommy_checklist_url = reverse("api:symptoms-mommy-checklist")
        self.mommy_selection_url = reverse("api:symptoms-mommy-selection")
        self.baby_checklist_url = reverse("api:symptoms-baby-checklist")
        self.baby_selection_url = reverse("api:symptoms-baby-selection")

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
