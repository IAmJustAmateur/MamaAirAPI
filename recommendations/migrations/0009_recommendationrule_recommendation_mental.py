from django.db import migrations, models


RULES = [
    {
        "rule_id": "mental.wellbeing.distressed",
        "version": 1,
        "title": "Take a moment to recover",
        "condition": "mood('distressed')",
        "alert": "You reported feeling distressed today.",
        "recommendation_mental": (
            "Pause non-essential tasks, move to a calm and safe place, and "
            "contact someone you trust if support would help."
        ),
        "severity": "moderate",
        "category": "lifestyle",
        "enabled": True,
        "priority": 50,
        "cooldown_hours": 24,
        "ttl_hours": 24,
    },
    {
        "rule_id": "mental.wellbeing.nervous",
        "version": 1,
        "title": "Take a calming pause",
        "condition": "mood('nervous') and not mood('distressed')",
        "alert": "You reported feeling nervous today.",
        "recommendation_mental": (
            "Sit somewhere comfortable and take slow, steady breaths for a few "
            "minutes. Continue when you feel ready."
        ),
        "severity": "info",
        "category": "lifestyle",
        "enabled": True,
        "priority": 52,
        "cooldown_hours": 24,
        "ttl_hours": 24,
    },
    {
        "rule_id": "mental.wellbeing.poor_sleep",
        "version": 1,
        "title": "Make room for rest",
        "condition": (
            "feeling('poor_sleep') and not "
            "any_of(mood('distressed'), mood('nervous'))"
        ),
        "alert": "You reported poor sleep today.",
        "recommendation_mental": (
            "Reduce non-essential tasks where possible and plan a short rest or "
            "an earlier bedtime."
        ),
        "severity": "info",
        "category": "lifestyle",
        "enabled": True,
        "priority": 54,
        "cooldown_hours": 24,
        "ttl_hours": 24,
    },
]


def seed_mental_rules(apps, schema_editor):
    RecommendationRule = apps.get_model("recommendations", "RecommendationRule")
    for data in RULES:
        lookup = {"rule_id": data["rule_id"], "version": data["version"]}
        defaults = {k: v for k, v in data.items() if k not in lookup}
        RecommendationRule.objects.update_or_create(defaults=defaults, **lookup)


def unseed_mental_rules(apps, schema_editor):
    RecommendationRule = apps.get_model("recommendations", "RecommendationRule")
    rule_ids = [item["rule_id"] for item in RULES]
    RecommendationRule.objects.filter(rule_id__in=rule_ids, version=1).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("recommendations", "0008_level3_recommendation_engine_rules"),
    ]

    operations = [
        migrations.AddField(
            model_name="recommendationrule",
            name="recommendation_mental",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.RunPython(seed_mental_rules, unseed_mental_rules),
    ]
