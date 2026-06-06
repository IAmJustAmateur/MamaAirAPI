from datetime import date
from django.test import TestCase
from api.models import User, RiskDefinition, UserRiskFactor, UserLifeStyle


class UserRiskCalculationTest(TestCase):
    def setUp(self):
        # Create user with minimal profile
        self.user = User.objects.create(
            email="testmom@example.com",
            weight_pre_pregnancy=70,
            height=165,
            date_of_birth=date(1995, 8, 2),
            race="caucasian",  # Assume this matches your choices
        )
        self.lifestyle = UserLifeStyle.objects.create(
            user=self.user,
            cooking_method="charcoal",
            diet_type="carnivore",
            work_type="desk",
            average_sleep_hours=7,
            activity_duration_minutes=120,
        )

    def test_user_risk_calculation(self):
        risks, integrated_risk = self.user.calculate_risk_factor_based_on_user_profile()

        self.assertIn("Preeclampsia", risks)

        # Calculate expected values manually:
        # BMI = 70 / (1.65^2) ≈ 25.71 → multiplier 2.8
        # Age = 2025 - 1995 = 30 → not > 30 → multiplier not applied
        expected_multiplier = 2.8

        self.assertAlmostEqual(risks["Preeclampsia"], expected_multiplier)
        self.assertAlmostEqual(risks["Hyperemesis"], 1.32)
        self.assertAlmostEqual(risks["Fetal Hypoxia"], 1.65)
        self.assertIn("Anemia", risks)
        self.assertIn("PROM", risks)
        self.assertIn("Cardiovascular Complications", risks)

    def test_new_profile_risk_matrix_for_underweight_african_teen(self):
        today = date.today()
        user = User.objects.create(
            email="risk-matrix-profile@example.com",
            weight_pre_pregnancy=45,
            height=165,
            date_of_birth=date(today.year - 18, 1, 1),
            race="african",
        )

        risks, _ = user.calculate_risk_factor_based_on_user_profile()

        self.assertAlmostEqual(risks["Anemia"], 1.57 * 1.45 * 2.10)
        self.assertAlmostEqual(risks["PROM"], 1.62 * 1.85)
        self.assertAlmostEqual(risks["Low Birth Weight"], 1.7 * 1.56 * 2.0)
        self.assertAlmostEqual(risks["Placental abruption"], 1.38 * 1.32)

    def test_lifestyle_risk_calculation(self):
        risks, integrated_risk = self.user.calculate_risk_factor_based_on_lifestyle()
        self.assertIn("Preeclampsia", risks)

    def test_new_lifestyle_risk_matrix_for_physical_low_activity_smoke(self):
        self.lifestyle.average_sleep_hours = 5
        self.lifestyle.activity_duration_minutes = 30
        self.lifestyle.work_type = "Physical"
        self.lifestyle.cooking_method = "charcoal"
        self.lifestyle.diet_type = "carnivore"
        self.lifestyle.save()

        risks, _ = self.user.calculate_risk_factor_based_on_lifestyle()

        self.assertAlmostEqual(risks["Anemia"], 1.38 * 1.30 * 1.55 * 1.68)
        self.assertAlmostEqual(risks["PROM"], 1.35 * 1.30 * 1.52 * 1.45)
        self.assertAlmostEqual(risks["Fetal Hypoxia"], 1.80 * 1.25 * 1.35 * 1.65)
        self.assertAlmostEqual(risks["Preeclampsia"], 1.4 * 2.2)

    def test_risk_calculations(self):
        risks, integrated_risk = self.user.calculate_risk_factors()
        self.assertIn("Preeclampsia", risks)

        # expected_multiplier = 2.8 * 2.2

        # self.assertAlmostEqual(risks["Preeclampsia"]["risk_value"], expected_multiplier)

    # def test_risk_with_missing_fields(self):
    #     user = User.objects.create(email="testmom_uncomplete@example.com")

    #     try:
    #         result = user.calculate_risk_factor_based_on_user_fields()
    #     except Exception as e:
    #         self.fail(f"Function raised an error with missing fields: {e}")

    def test_get_mommy_symptoms_for_checking(self):
        risks_symptoms = self.user.get_mommy_symptoms_for_checking()
        self.assertIsInstance(risks_symptoms, list)
        self.assertEqual(len(risks_symptoms), 5)

        # self.assertIn("Preeclampsia", risks_symptoms)
