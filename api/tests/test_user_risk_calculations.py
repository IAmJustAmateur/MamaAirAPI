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
        )

    def test_user_risk_calculation(self):
        risks = self.user.calculate_risk_factor_based_on_user_fields()

        self.assertIn("Preeclampsia", risks)

        # Calculate expected values manually:
        # BMI = 70 / (1.65^2) ≈ 25.71 → multiplier 2.8
        # Age = 2025 - 1995 = 30 → not > 30 → multiplier not applied
        expected_multiplier = 2.8

        self.assertAlmostEqual(risks["Preeclampsia"], expected_multiplier)

    def test_lifestyle_risk_calculation(self):
        risks = self.user.calculate_risk_factor_based_on_lifestyle()
        self.assertIn("Preeclampsia", risks)

        expected_multiplier = 2.2

        self.assertAlmostEqual(risks["Preeclampsia"], expected_multiplier)

    def test_risk_calculations(self):
        risks = self.user.calculate_risk_factors()
        self.assertIn("Preeclampsia", risks)

        expected_multiplier = round(2.8 * 2.2, 1)

        self.assertAlmostEqual(risks["Preeclampsia"], expected_multiplier)

    # def test_risk_with_missing_fields(self):
    #     user = User.objects.create(email="testmom_uncomplete@example.com")

    #     try:
    #         result = user.calculate_risk_factor_based_on_user_fields()
    #     except Exception as e:
    #         self.fail(f"Function raised an error with missing fields: {e}")

    def test_get_mommy_symptoms_for_checking(self):
        risks_symptoms = self.user.get_mommy_symptoms_for_checking()

        self.assertIn("Preeclampsia", risks_symptoms)
