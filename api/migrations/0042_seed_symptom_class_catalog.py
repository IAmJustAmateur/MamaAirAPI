from django.db import migrations


def _upsert_risk(RiskDefinition, name, priority):
    risk, _ = RiskDefinition.objects.update_or_create(
        name=name,
        defaults={
            "description": "",
            "is_enabled": True,
            "priority": priority,
        },
    )
    return risk


def _upsert_symptom(SymptomModel, name):
    symptom, _ = SymptomModel.objects.get_or_create(name=name)
    return symptom


def _link(LinkModel, risk, symptom, symptom_class, source_phrase):
    LinkModel.objects.update_or_create(
        risk_definition=risk,
        symptom=symptom,
        defaults={
            "symptom_class": symptom_class,
            "source_phrase": source_phrase,
        },
    )


def seed_symptom_class_catalog(apps, schema_editor):
    RiskDefinition = apps.get_model("api", "RiskDefinition")
    MommySymptom = apps.get_model("api", "MommySymptom")
    BabySymptom = apps.get_model("api", "BabySymptom")
    RiskDefinitionMommySymptom = apps.get_model("api", "RiskDefinitionMommySymptom")
    RiskDefinitionBabySymptom = apps.get_model("api", "RiskDefinitionBabySymptom")

    risks = {
        "Preeclampsia": _upsert_risk(RiskDefinition, "Preeclampsia", 1),
        "Preterm birth": _upsert_risk(RiskDefinition, "Preterm birth", 2),
        "GDM": _upsert_risk(RiskDefinition, "GDM", 3),
        "Low Birth Weight": _upsert_risk(RiskDefinition, "Low Birth Weight", 4),
        "Placental abruption": _upsert_risk(
            RiskDefinition, "Placental abruption", 5
        ),
        "Anemia": _upsert_risk(RiskDefinition, "Anemia", 6),
        "PROM": _upsert_risk(RiskDefinition, "PROM", 7),
        "Hyperemesis": _upsert_risk(RiskDefinition, "Hyperemesis", 8),
        "Cardiovascular Complications": _upsert_risk(
            RiskDefinition, "Cardiovascular Complications", 9
        ),
        "Fetal Hypoxia": _upsert_risk(RiskDefinition, "Fetal Hypoxia", 10),
    }

    mommy_links = [
        ("Preeclampsia", "high blood pressure", 1, "High blood pressure"),
        ("Preeclampsia", "persistent headache", 2, "Persistent headache"),
        ("Preeclampsia", "upper abdominal pain", 2, "Upper abdominal pain"),
        ("Preeclampsia", "blurred vision", 2, "Blurred vision"),
        (
            "Preeclampsia",
            "severe swelling of the face or hands",
            2,
            "Severe swelling of the face or hands",
        ),
        (
            "Preterm birth",
            "contraction frequency",
            1,
            "Contraction frequency (>1 in 10 min)",
        ),
        ("Preterm birth", "vaginal bleeding", 1, "Vaginal bleeding"),
        (
            "Preterm birth",
            "non-specific abdominal pain",
            4,
            "Non-specific abdominal or back pain",
        ),
        (
            "Preterm birth",
            "non-specific back pain",
            4,
            "Non-specific abdominal or back pain",
        ),
        (
            "Preterm birth",
            "increased heart rate",
            2,
            "Increased heart rate and fever",
        ),
        ("Preterm birth", "fever", 2, "Increased heart rate and fever"),
        ("GDM", "increased thirst", 2, "Increased thirst"),
        ("GDM", "increased urination", 2, "Increased urination"),
        ("GDM", "blurred eyesight", 2, "Blurred eyesight and dry mouth"),
        ("GDM", "dry mouth", 2, "Blurred eyesight and dry mouth"),
        (
            "GDM",
            "persistent tiredness",
            2,
            "Persistent tiredness or fatigue",
        ),
        ("GDM", "fatigue", 2, "Persistent tiredness or fatigue"),
        ("GDM", "rapid weight gain", 2, "Rapid weight gain (>1kg in week)"),
        ("Placental abruption", "vaginal bleeding", 1, "Vaginal bleeding"),
        (
            "Placental abruption",
            "severe abdominal pain",
            1,
            "Severe abdominal pain",
        ),
        (
            "Placental abruption",
            "uterine tenderness",
            1,
            "Uterine tenderness or rigidity",
        ),
        (
            "Placental abruption",
            "uterine rigidity",
            1,
            "Uterine tenderness or rigidity",
        ),
        (
            "Placental abruption",
            "contraction frequency",
            1,
            "Contraction frequency (>1 in 10 min)",
        ),
        ("Placental abruption", "lower back pain", 4, "Lower back pain"),
        ("Anemia", "persistent fatigue", 2, "Persistent fatigue or weakness"),
        ("Anemia", "weakness", 2, "Persistent fatigue or weakness"),
        (
            "Anemia",
            "pallor",
            2,
            "Pallor (skin, nails or conjunctiva)",
        ),
        (
            "Anemia",
            "shortness of breath on exertion",
            2,
            "Shortness of breath on exertion",
        ),
        (
            "Anemia",
            "dizziness",
            2,
            "Dizziness or lightheadedness",
        ),
        (
            "Anemia",
            "lightheadedness",
            2,
            "Dizziness or lightheadedness",
        ),
        (
            "Anemia",
            "rapid heartbeat",
            2,
            "Rapid or irregular heartbeat",
        ),
        (
            "Anemia",
            "irregular heartbeat",
            2,
            "Rapid or irregular heartbeat",
        ),
        ("PROM", "leaking fluid", 1, "Leaking fluid"),
        ("Hyperemesis", "severe vomiting", 2, "Severe vomiting (>5 times in day)"),
        (
            "Cardiovascular Complications",
            "chest pain",
            1,
            "Chest pain and heart palpitations",
        ),
        (
            "Cardiovascular Complications",
            "heart palpitations",
            1,
            "Chest pain and heart palpitations",
        ),
        (
            "Low Birth Weight",
            "no visible belly growth",
            3,
            "No visible belly growth",
        ),
        (
            "Low Birth Weight",
            "low maternal weight gain",
            3,
            "Low maternal weight gain (<300g in week)",
        ),
        (
            "Low Birth Weight",
            "poor appetite",
            3,
            "Poor maternal appetite",
        ),
    ]

    baby_links = [
        ("Preeclampsia", "reduced fetal movement", 3, "Reduced fetal movement"),
        ("Preterm birth", "reduced fetal movement", 3, "Reduced fetal movement"),
        ("Low Birth Weight", "reduced fetal movement", 3, "Reduced fetal movement"),
        ("Fetal Hypoxia", "reduced kicks", 3, "Reduced kicks (5-9 in 2 hours)"),
        (
            "Fetal Hypoxia",
            "severely reduced kicks",
            1,
            "Severely reduced kicks (<5 in 2 hours)",
        ),
        (
            "Fetal Hypoxia",
            "prolonged stillness",
            1,
            "Prolonged stillness (>4 hours)",
        ),
        (
            "Fetal Hypoxia",
            "excessive hiccups",
            3,
            "Excessive hiccups (>5 episodes in day)",
        ),
        (
            "Low Birth Weight",
            "reduced fetal rolling or stretching",
            3,
            "Reduced fetal rolling or stretching (<1 time in day)",
        ),
        (
            "Low Birth Weight",
            "reduced kicking patterns",
            3,
            "Reduced kicking patterns",
        ),
    ]

    for risk_name, symptom_name, symptom_class, source_phrase in mommy_links:
        _link(
            RiskDefinitionMommySymptom,
            risks[risk_name],
            _upsert_symptom(MommySymptom, symptom_name),
            symptom_class,
            source_phrase,
        )

    for risk_name, symptom_name, symptom_class, source_phrase in baby_links:
        _link(
            RiskDefinitionBabySymptom,
            risks[risk_name],
            _upsert_symptom(BabySymptom, symptom_name),
            symptom_class,
            source_phrase,
        )


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0041_symptom_link_classes"),
    ]

    operations = [
        migrations.RunPython(seed_symptom_class_catalog, migrations.RunPython.noop),
    ]
