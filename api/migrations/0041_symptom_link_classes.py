from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0040_wellbeing_emoji"),
    ]

    operations = [
        migrations.AddField(
            model_name="riskdefinitionmommysymptom",
            name="source_phrase",
            field=models.CharField(blank=True, default="", max_length=512),
        ),
        migrations.AddField(
            model_name="riskdefinitionmommysymptom",
            name="symptom_class",
            field=models.PositiveSmallIntegerField(
                choices=[
                    (1, "Acute & Emergency Indicators"),
                    (2, "Condition-Specific Systemic Indicators"),
                    (3, "Fetal Activity & Growth Markers"),
                    (4, "Lifestyle & Environmental Stressors"),
                ],
                default=2,
            ),
        ),
        migrations.AddField(
            model_name="riskdefinitionbabysymptom",
            name="source_phrase",
            field=models.CharField(blank=True, default="", max_length=512),
        ),
        migrations.AddField(
            model_name="riskdefinitionbabysymptom",
            name="symptom_class",
            field=models.PositiveSmallIntegerField(
                choices=[
                    (1, "Acute & Emergency Indicators"),
                    (2, "Condition-Specific Systemic Indicators"),
                    (3, "Fetal Activity & Growth Markers"),
                    (4, "Lifestyle & Environmental Stressors"),
                ],
                default=3,
            ),
        ),
    ]
