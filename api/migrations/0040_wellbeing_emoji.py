from django.db import migrations, models


WELLBEING_EMOJI = {
    "feel_sick": "🤒",
    "distressed": "😣",
    "nervous": "😟",
    "nauseous": "🤢",
    "everything_is_fine": "🙂",
    "poor_sleep": "😴",
    "headache": "🤕",
}


def populate_wellbeing_emoji(apps, schema_editor):
    Wellbeing = apps.get_model("api", "Wellbeing")
    for code, emoji in WELLBEING_EMOJI.items():
        Wellbeing.objects.filter(code=code).update(emoji=emoji)


def clear_wellbeing_emoji(apps, schema_editor):
    Wellbeing = apps.get_model("api", "Wellbeing")
    Wellbeing.objects.filter(code__in=WELLBEING_EMOJI.keys()).update(emoji="")


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0039_water_units_ml"),
    ]

    operations = [
        migrations.AddField(
            model_name="wellbeing",
            name="emoji",
            field=models.CharField(blank=True, default="", max_length=16),
        ),
        migrations.RunPython(populate_wellbeing_emoji, clear_wellbeing_emoji),
    ]
