from django.db import migrations, models


FL_OZ_TO_ML = 29.5735295625


def convert_water_units_to_ml(apps, schema_editor):
    Wellbeing = apps.get_model("api", "Wellbeing")
    UserWellbeingLog = apps.get_model("api", "UserWellbeingLog")

    for water_goal in Wellbeing.objects.filter(kind="water_goal"):
        if water_goal.unit == "fl_oz" and water_goal.number_value is not None:
            water_goal.number_value = round(
                water_goal.number_value * FL_OZ_TO_ML / 10
            ) * 10
        water_goal.unit = "ml"
        water_goal.save(update_fields=["number_value", "unit"])

    for log in UserWellbeingLog.objects.filter(water_unit="fl_oz"):
        log.water_amount = round(log.water_amount * FL_OZ_TO_ML, 2)
        log.water_unit = "ml"
        log.save(update_fields=["water_amount", "water_unit"])


def convert_water_units_to_fl_oz(apps, schema_editor):
    Wellbeing = apps.get_model("api", "Wellbeing")
    UserWellbeingLog = apps.get_model("api", "UserWellbeingLog")

    for water_goal in Wellbeing.objects.filter(kind="water_goal", unit="ml"):
        if water_goal.number_value is not None:
            water_goal.number_value = round(water_goal.number_value / FL_OZ_TO_ML)
        water_goal.unit = "fl_oz"
        water_goal.save(update_fields=["number_value", "unit"])

    for log in UserWellbeingLog.objects.filter(water_unit="ml"):
        log.water_amount = round(log.water_amount / FL_OZ_TO_ML, 2)
        log.water_unit = "fl_oz"
        log.save(update_fields=["water_amount", "water_unit"])


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0038_dailytask_userdailytaskcompletion"),
    ]

    operations = [
        migrations.AlterField(
            model_name="wellbeing",
            name="unit",
            field=models.CharField(blank=True, default="ml", max_length=16),
        ),
        migrations.AlterField(
            model_name="userwellbeinglog",
            name="water_unit",
            field=models.CharField(default="ml", max_length=16),
        ),
        migrations.RunPython(convert_water_units_to_ml, convert_water_units_to_fl_oz),
    ]
