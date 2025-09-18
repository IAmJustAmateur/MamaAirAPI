from django.db import migrations


# Поля: rule_id, version, title, condition, message, severity, category,
#        enabled, priority (меньше — важнее), cooldown_hours, ttl_hours
RULES = [
    # === MEDICAL (critical) ===
    {
        "rule_id": "alert.placental_abruption",
        "version": 1,
        "title": "Possible placental abruption",
        "condition": (
            "count_true("
            "m('vaginal bleeding'), "
            "m('abdominal pain'), "
            "m('lower back pain'), "
            "m('contractions'), "
            "m('uterine tenderness'), "
            "m('uterine rigidity')"
            ") >= 3"
        ),
        "message": "Call your doctor immediately; possible placental abruption.",
        "severity": "critical",
        "category": "medical",
        "enabled": True,
        "priority": 5,  # critical
        "cooldown_hours": 24,
        "ttl_hours": 24,
    },
    {
        "rule_id": "alert.preeclampsia",
        "version": 1,
        "title": "Possible preeclampsia",
        "condition": (
            "count_true("
            "is_20w_plus, "
            "m('high blood pressure'), "
            "m('headache'), "
            "m('upper abdominal pain'), "
            "b('reduced fetal movement')"
            ") >= 3"
        ),
        "message": "Contact your doctor today, possible preeclampsia.",
        "severity": "critical",
        "category": "medical",
        "enabled": True,
        "priority": 6,  # critical
        "cooldown_hours": 24,
        "ttl_hours": 24,
    },
    {
        "rule_id": "alert.preterm_labor",
        "version": 1,
        "title": "Signs of preterm labor",
        "condition": (
            "count_true("
            "m('contractions_gt_1_per_10min'), "
            "m('increased heart rate'), "
            "m('abdominal or back pain'), "
            "m('fever'), "
            "m('vaginal bleeding')"
            ") >= 3"
        ),
        "message": "Call your maternity doctor, signs of preterm labor.",
        "severity": "critical",
        "category": "medical",
        "enabled": True,
        "priority": 7,  # critical
        "cooldown_hours": 24,
        "ttl_hours": 24,
    },
    # === MEDICAL (high) ===
    {
        "rule_id": "alert.gdm",
        "version": 1,
        "title": "Possible gestational diabetes (GDM)",
        "condition": (
            "count_true("
            "m('increased thirst'), "
            "m('increased urination'), "
            "m('blurred eyesight'), "
            "m('dried mouth'), "
            "m('tiredness')"
            ") >= 3"
        ),
        "message": "Book a glucose test; possible gestational diabetes.",
        "severity": "high",
        "category": "medical",
        "enabled": True,
        "priority": 20,  # high
        "cooldown_hours": 24,
        "ttl_hours": 24,
    },
    {
        "rule_id": "alert.lbw",
        "version": 1,
        "title": "Possible low birth weight risk",
        "condition": (
            "count_true("
            "b('reduced fetal movement'), "
            "m('no belly growth'), "
            "m('dizziness'), "
            "m('poor appetite')"
            ") >= 3"
        ),
        "message": "Review diet and call your doctor; possible low birth weight risk.",
        "severity": "high",
        "category": "medical",
        "enabled": True,
        "priority": 22,  # high
        "cooldown_hours": 24,
        "ttl_hours": 24,
    },
    # === AIR QUALITY (moderate) ===
    {
        "rule_id": "alert.pm25.daily",
        "version": 1,
        "title": "PM2.5 is high",
        "condition": "ge_poll('pm25_avg_24h', 10)",
        "message": "PM2.5 is high. Limit outdoor time, use a mask/purifier, ventilate when cleaner.",
        "severity": "moderate",
        "category": "air_quality",
        "enabled": True,
        "priority": 30,  # moderate
        "cooldown_hours": 12,
        "ttl_hours": 12,
    },
    {
        "rule_id": "alert.no2.daily",
        "version": 1,
        "title": "NO₂ is high",
        "condition": "ge_poll('no2_24h_mean', 25)",
        "message": "NO₂ is high. Avoid traffic hotspots; ventilate away from road emissions.",
        "severity": "moderate",
        "category": "air_quality",
        "enabled": True,
        "priority": 32,  # moderate
        "cooldown_hours": 12,
        "ttl_hours": 12,
    },
    {
        "rule_id": "alert.o3.8h",
        "version": 1,
        "title": "Ozone (O₃) is high",
        "condition": "ge_poll('o3_8h_max', 100)",
        "message": "Ozone is high. Shift outdoor activity to morning/evening; avoid vigorous exercise outdoors.",
        "severity": "moderate",
        "category": "air_quality",
        "enabled": True,
        "priority": 34,  # moderate
        "cooldown_hours": 12,
        "ttl_hours": 12,
    },
    {
        "rule_id": "alert.so2.daily",
        "version": 1,
        "title": "SO₂ is high",
        "condition": "ge_poll('so2_24h_mean', 40)",
        "message": "SO₂ is high. Avoid heavy traffic/industrial plumes; close windows during peaks.",
        "severity": "moderate",
        "category": "air_quality",
        "enabled": True,
        "priority": 36,  # moderate
        "cooldown_hours": 12,
        "ttl_hours": 12,
    },
    # === LIFESTYLE / PROFILE ===
    {
        "rule_id": "alert.sleep.low",
        "version": 1,
        "title": "Low sleep in last 24h / week",
        "condition": (
            "(exists(lifestyle.get('average_sleep_hours')) and "
            "lifestyle.get('average_sleep_hours') < 6) "
            "or "
            "(exists(lifestyle.get('avg_sleep_7d')) and "
            "lifestyle.get('avg_sleep_7d') < 7)"
        ),
        "message": "Prioritize rest today; target 7–9 h/night. Reduce exertion and screen time; consider a 20–30 min nap.",
        "severity": "moderate",
        "category": "lifestyle",
        "enabled": True,
        "priority": 50,  # lifestyle/moderate
        "cooldown_hours": 24,
        "ttl_hours": 24,
    },
    {
        "rule_id": "alert.bmi.low",
        "version": 1,
        "title": "Low pre-pregnancy BMI",
        "condition": "exists(profile.get('bmi')) and profile.get('bmi') < 18.5",
        "message": "Increase energy/protein intake and focus on a nutritious diet.",
        "severity": "moderate",
        "category": "general",
        "enabled": True,
        "priority": 60,  # profile
        "cooldown_hours": 168,  # 7 days
        "ttl_hours": 168,
    },
    {
        "rule_id": "alert.bmi.high",
        "version": 1,
        "title": "High pre-pregnancy BMI",
        "condition": "exists(profile.get('bmi')) and profile.get('bmi') >= 30",
        "message": "Limit added sugars, and aim for ≥150 min/week of moderate activity.",
        "severity": "moderate",
        "category": "general",
        "enabled": True,
        "priority": 61,  # profile
        "cooldown_hours": 168,
        "ttl_hours": 168,
    },
    {
        "rule_id": "alert.cooking.solid_fuel",
        "version": 1,
        "title": "Solid-fuel cooking (wood/charcoal)",
        "condition": "lifestyle.get('cooking_method') in ('wood', 'charcoal')",
        "message": "If you use wood/charcoal, improve ventilation and consider switching to cleaner stove/fuel when possible.",
        "severity": "moderate",
        "category": "lifestyle",
        "enabled": True,
        "priority": 65,  # lifestyle
        "cooldown_hours": 168,
        "ttl_hours": 168,
    },
    {
        "rule_id": "alert.cooking.gas_and_no2_high",
        "version": 1,
        "title": "Gas cooking with high outdoor NO₂",
        "condition": "lifestyle.get('cooking_method') == 'gas' and ge_poll('no2_24h_mean', 25)",
        "message": "Outdoor NO₂ is high. When cooking on gas, use a hood or open windows to improve ventilation.",
        "severity": "info",
        "category": "lifestyle",
        "enabled": True,
        "priority": 66,  # lifestyle/AQ
        "cooldown_hours": 48,
        "ttl_hours": 48,
    },
    {
        "rule_id": "alert.exercise.low",
        "version": 1,
        "title": "Low weekly activity",
        "condition": (
            "exists(lifestyle.get('activity_duration_minutes')) and "
            "lifestyle.get('activity_duration_minutes') < 150"
        ),
        "message": "Aim for ≥150 min/week of moderate activity (e.g., 30 min × 5 days); start with gentle walks today.",
        "severity": "info",
        "category": "lifestyle",
        "enabled": True,
        "priority": 68,  # lifestyle
        "cooldown_hours": 168,
        "ttl_hours": 168,
    },
]


def seed_rules(apps, schema_editor):
    RecommendationRule = apps.get_model("recommendations", "RecommendationRule")
    for data in RULES:
        lookup = {"rule_id": data["rule_id"], "version": data["version"]}
        defaults = {k: v for k, v in data.items() if k not in lookup}
        RecommendationRule.objects.update_or_create(defaults=defaults, **lookup)


def unseed_rules(apps, schema_editor):
    RecommendationRule = apps.get_model("recommendations", "RecommendationRule")
    from django.db.models import Q

    q = Q()
    for data in RULES:
        q |= Q(rule_id=data["rule_id"], version=data["version"])
    if q:
        RecommendationRule.objects.filter(q).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("recommendations", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_rules, unseed_rules),
    ]
