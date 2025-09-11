from django.test import TestCase

from api.services.aggregation import agg_max_plus_logistic_tail


class AggregationTest(TestCase):
    def test_aggregation(self):
        risk_factors_sets = [
            {
                "Preeclampsia": 2.8,
                "Preterm birth": 1.5,
                "GDM": 1.3,
                "Low Birth Weight": 1.2,
            },
            {
                "Preeclampsia": 1.6,
                "Preterm birth": 1.5,
                "GDM": 1.4,
                "Low Birth Weight": 1.3,
            },
            {
                "Preeclampsia": 6,
                "Preterm birth": 7,
                "GDM": 7.5,
                "Low Birth Weight": 8,
            },
            {
                "Preeclampsia": 1.1,
                "Preterm birth": 1.1,
                "GDM": 1.1,
                "Low Birth Weight": 1.1,
            },
            {
                "Preeclampsia": 9,
                "Preterm birth": 9,
                "GDM": 9,
                "Low Birth Weight": 9,
            },
        ]
        for risk_factors in risk_factors_sets:
            aggregated = agg_max_plus_logistic_tail(
                risk_factors, mid=4.0, sensitivity=0.7
            )
            max_risk = max(risk_factors.values())
            self.assertGreater(aggregated, max_risk)
            self.assertLessEqual(aggregated, 10.0)  # Rmax default is 10.0
            risk_product = 1.0
            for v in risk_factors.values():
                risk_product *= v
            self.assertLess(aggregated, risk_product)  # should be less than product
