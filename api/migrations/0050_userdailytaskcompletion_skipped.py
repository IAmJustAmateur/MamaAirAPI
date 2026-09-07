from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0049_dailyplan_dailyaction_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="userdailytaskcompletion",
            name="skipped",
            field=models.BooleanField(default=False),
        ),
        migrations.AddConstraint(
            model_name="userdailytaskcompletion",
            constraint=models.CheckConstraint(
                condition=~models.Q(completed=True, skipped=True),
                name="task_completion_not_completed_and_skipped",
            ),
        ),
    ]
