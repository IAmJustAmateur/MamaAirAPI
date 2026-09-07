from django.db import migrations, models


DIMENSION_CHOICES = [
    ("diet", "Diet"),
    ("activity", "Activity"),
    ("behavior", "Behavior"),
    ("mental", "Mental"),
]


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0050_userdailytaskcompletion_skipped"),
    ]

    operations = [
        migrations.AlterField(
            model_name="recommendationcompletion",
            name="dimension",
            field=models.CharField(max_length=16, choices=DIMENSION_CHOICES),
        ),
        migrations.AlterField(
            model_name="dailyaction",
            name="source_dimension",
            field=models.CharField(
                max_length=16,
                choices=DIMENSION_CHOICES,
                null=True,
                blank=True,
            ),
        ),
    ]
