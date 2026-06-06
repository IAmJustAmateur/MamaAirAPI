from django.db import migrations


RISK_PRIORITIES = {
    "Preeclampsia": 1,
    "Preterm birth": 2,
    "GDM": 3,
    "Low Birth Weight": 4,
    "Placental abruption": 5,
    "Anemia": 6,
    "PROM": 7,
    "Hyperemesis": 8,
    "Cardiovascular Complications": 9,
    "Fetal Hypoxia": 10,
}


PROFILE_FACTORS = [
    # Preeclampsia
    ("Preeclampsia", "bmi>=25", 2.8),
    ("Preeclampsia", "full_year>=35", 1.8),
    ("Preeclampsia", "'race'=='african'", 1.6),
    # Preterm birth
    ("Preterm birth", "full_year<=16", 1.5),
    ("Preterm birth", "full_year>35 and full_year<=40", 1.2),
    ("Preterm birth", "full_year>40", 1.4),
    ("Preterm birth", "bmi<18.5", 1.07),
    # GDM
    ("GDM", "bmi>=30", 4.0),
    ("GDM", "'race'=='african'", 1.11),
    # Low Birth Weight
    ("Low Birth Weight", "full_year<20", 1.56),
    ("Low Birth Weight", "bmi<19", 1.7),
    ("Low Birth Weight", "'race'=='african'", 2.0),
    # Placental abruption
    ("Placental abruption", "full_year>=35", 1.62),
    ("Placental abruption", "bmi<18.5", 1.38),
    ("Placental abruption", "'race'=='african'", 1.32),
    # Anemia
    ("Anemia", "bmi<18.5", 1.57),
    ("Anemia", "full_year<19 or full_year>=40", 1.45),
    ("Anemia", "'race'=='african'", 2.10),
    # PROM
    ("PROM", "bmi<18.5", 1.62),
    ("PROM", "full_year>=35", 1.32),
    ("PROM", "'race'=='african'", 1.85),
    # Hyperemesis
    ("Hyperemesis", "bmi>=25", 1.32),
    ("Hyperemesis", "full_year<19", 1.41),
    ("Hyperemesis", "'race'=='african'", 1.53),
    # Cardiovascular Complications
    ("Cardiovascular Complications", "bmi>=30", 1.95),
    ("Cardiovascular Complications", "full_year>35", 1.35),
    ("Cardiovascular Complications", "'race'=='african'", 1.54),
    # Fetal Hypoxia
    ("Fetal Hypoxia", "bmi>=25", 1.65),
    ("Fetal Hypoxia", "full_year>35", 1.40),
    ("Fetal Hypoxia", "'race'=='african'", 1.50),
]


LIFESTYLE_FACTORS = [
    # Preeclampsia
    ("Preeclampsia", "average_sleep_hours<=6", 1.4),
    ("Preeclampsia", "activity_duration_minutes>=420", 0.76),
    ("Preeclampsia", "'work_type'=='Night Shift'", 1.75),
    (
        "Preeclampsia",
        "'cooking_method'=='wood' or 'cooking_method'=='charcoal'",
        2.2,
    ),
    # Preterm birth
    ("Preterm birth", "average_sleep_hours<6", 1.23),
    ("Preterm birth", "'work_type'=='Night Shift'", 1.21),
    (
        "Preterm birth",
        "'cooking_method'=='wood' or 'cooking_method'=='charcoal'",
        1.3,
    ),
    # GDM
    ("GDM", "average_sleep_hours<7", 1.75),
    ("GDM", "'work_type'=='Night Shift'", 1.75),
    ("GDM", "activity_duration_minutes>=150", 0.7),
    ("GDM", "'diet_type'=='vegetarian'", 1.09),
    # Low Birth Weight
    ("Low Birth Weight", "'work_type'=='Night Shift'", 1.18),
    (
        "Low Birth Weight",
        "'cooking_method'=='wood' or 'cooking_method'=='charcoal'",
        1.74,
    ),
    # Placental abruption
    ("Placental abruption", "average_sleep_hours>9 or average_sleep_hours<6", 1.3),
    ("Placental abruption", "'work_type'=='Desk'", 17.3),
    # Anemia
    ("Anemia", "average_sleep_hours<=6", 1.38),
    ("Anemia", "activity_duration_minutes<420", 1.30),
    ("Anemia", "'work_type'=='Physical'", 1.55),
    ("Anemia", "'cooking_method'=='wood' or 'cooking_method'=='charcoal'", 1.68),
    # PROM
    ("PROM", "average_sleep_hours<=6", 1.35),
    ("PROM", "activity_duration_minutes<420", 1.30),
    ("PROM", "'work_type'=='Physical'", 1.52),
    ("PROM", "'cooking_method'=='wood' or 'cooking_method'=='charcoal'", 1.45),
    # Hyperemesis
    ("Hyperemesis", "average_sleep_hours<=6", 1.45),
    ("Hyperemesis", "activity_duration_minutes<420", 1.18),
    ("Hyperemesis", "'work_type'=='Night Shift'", 1.36),
    (
        "Hyperemesis",
        "'cooking_method'=='wood' or 'cooking_method'=='charcoal'",
        1.38,
    ),
    # Cardiovascular Complications
    ("Cardiovascular Complications", "average_sleep_hours<=6", 1.42),
    ("Cardiovascular Complications", "activity_duration_minutes<420", 1.35),
    ("Cardiovascular Complications", "'work_type'=='Night Shift'", 1.48),
    (
        "Cardiovascular Complications",
        "'cooking_method'=='wood' or 'cooking_method'=='charcoal'",
        1.65,
    ),
    # Fetal Hypoxia
    ("Fetal Hypoxia", "average_sleep_hours<=6", 1.80),
    ("Fetal Hypoxia", "activity_duration_minutes<420", 1.25),
    ("Fetal Hypoxia", "'work_type'=='Physical'", 1.35),
    (
        "Fetal Hypoxia",
        "'cooking_method'=='wood' or 'cooking_method'=='charcoal'",
        1.65,
    ),
]


def _upsert_risks(RiskDefinition):
    risks = {}
    for name, priority in RISK_PRIORITIES.items():
        risk, _ = RiskDefinition.objects.update_or_create(
            name=name,
            defaults={
                "description": "",
                "is_enabled": True,
                "priority": priority,
            },
        )
        risks[name] = risk
    return risks


def _replace_factors(FactorModel, risks, factors):
    FactorModel.objects.filter(risk__name__in=RISK_PRIORITIES.keys()).delete()
    FactorModel.objects.bulk_create(
        [
            FactorModel(
                risk=risks[risk_name],
                condition=condition,
                multiplier=multiplier,
            )
            for risk_name, condition, multiplier in factors
        ]
    )


def seed_risk_factor_matrix(apps, schema_editor):
    RiskDefinition = apps.get_model("api", "RiskDefinition")
    UserRiskFactor = apps.get_model("api", "UserRiskFactor")
    LifestyleRiskFactor = apps.get_model("api", "LifestyleRiskFactor")

    risks = _upsert_risks(RiskDefinition)
    _replace_factors(UserRiskFactor, risks, PROFILE_FACTORS)
    _replace_factors(LifestyleRiskFactor, risks, LIFESTYLE_FACTORS)


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0042_seed_symptom_class_catalog"),
    ]

    operations = [
        migrations.RunPython(seed_risk_factor_matrix, migrations.RunPython.noop),
    ]
