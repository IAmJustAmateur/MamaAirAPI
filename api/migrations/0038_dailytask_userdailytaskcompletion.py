# Generated manually on 2026-05-03

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def seed_daily_tasks(apps, schema_editor):
    DailyTask = apps.get_model("api", "DailyTask")
    tasks = [
        ("drink_water", "Drink water", 10),
        ("cooking_smoke", "Cooking Smoke", 20),
        ("morning_walk", "Morning Walk", 30),
    ]
    for code, title, sort_order in tasks:
        DailyTask.objects.update_or_create(
            code=code,
            defaults={
                "title": title,
                "sort_order": sort_order,
                "is_active": True,
            },
        )


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0037_dailycheckin"),
    ]

    operations = [
        migrations.CreateModel(
            name="DailyTask",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("code", models.SlugField(max_length=64, unique=True)),
                ("title", models.CharField(max_length=255)),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "ordering": ["sort_order", "title"],
            },
        ),
        migrations.CreateModel(
            name="UserDailyTaskCompletion",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("date", models.DateField()),
                ("completed", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "task",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="completions",
                        to="api.dailytask",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="task_completions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-date", "task__sort_order", "task__title"],
            },
        ),
        migrations.AddIndex(
            model_name="userdailytaskcompletion",
            index=models.Index(
                fields=["user", "date"], name="api_userdai_user_id_52c953_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="userdailytaskcompletion",
            index=models.Index(
                fields=["user", "task", "date"],
                name="api_userdai_user_id_9df84f_idx",
            ),
        ),
        migrations.AddConstraint(
            model_name="userdailytaskcompletion",
            constraint=models.UniqueConstraint(
                fields=("user", "task", "date"),
                name="uniq_user_task_completion_date",
            ),
        ),
        migrations.RunPython(seed_daily_tasks, migrations.RunPython.noop),
    ]
