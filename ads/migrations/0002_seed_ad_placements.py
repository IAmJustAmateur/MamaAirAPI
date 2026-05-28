from django.db import migrations


PLACEMENTS = [
    ("day_entry", "Вход в день"),
    ("digital_twin_baby", "Digital twin baby"),
]


def seed_ad_placements(apps, schema_editor):
    AdPlacement = apps.get_model("ads", "AdPlacement")
    for code, name in PLACEMENTS:
        AdPlacement.objects.update_or_create(
            code=code,
            defaults={"name": name, "is_active": True},
        )


def remove_ad_placements(apps, schema_editor):
    AdPlacement = apps.get_model("ads", "AdPlacement")
    AdPlacement.objects.filter(code__in=[code for code, _name in PLACEMENTS]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("ads", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_ad_placements, remove_ad_placements),
    ]
