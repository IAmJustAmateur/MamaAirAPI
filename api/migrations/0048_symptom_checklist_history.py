import uuid

from django.db import migrations, models
import django.db.models.deletion
from django.utils.text import slugify


def populate_symptom_codes(apps, schema_editor):
    for model_name, namespace in (
        ("MommySymptom", "mommy"),
        ("BabySymptom", "baby"),
    ):
        Symptom = apps.get_model("api", model_name)
        generated_codes = set()
        updates = []

        for symptom in Symptom.objects.order_by("pk"):
            slug = slugify(symptom.name).replace("-", "_")
            if not slug:
                raise RuntimeError(
                    f"Cannot generate a stable code for {model_name} {symptom.pk}"
                )
            code = f"{namespace}.{slug}"
            if code in generated_codes:
                raise RuntimeError(
                    f"Stable symptom code collision in {model_name}: {code}"
                )
            generated_codes.add(code)
            symptom.code = code
            updates.append(symptom)

        if updates:
            Symptom.objects.bulk_update(updates, ["code"])


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0047_movement_location_security"),
    ]

    operations = [
        migrations.AddField(
            model_name="mommysymptom",
            name="code",
            field=models.CharField(max_length=255, null=True),
        ),
        migrations.AddField(
            model_name="babysymptom",
            name="code",
            field=models.CharField(max_length=255, null=True),
        ),
        migrations.RunPython(populate_symptom_codes, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="mommysymptom",
            name="code",
            field=models.CharField(max_length=255, unique=True),
        ),
        migrations.AlterField(
            model_name="babysymptom",
            name="code",
            field=models.CharField(max_length=255, unique=True),
        ),
        migrations.CreateModel(
            name="GeneratedSymptomChecklist",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                (
                    "checklist_type",
                    models.CharField(
                        choices=[("mommy", "Mommy"), ("baby", "Baby")],
                        max_length=16,
                    ),
                ),
                ("local_date", models.DateField()),
                ("generated_at", models.DateTimeField(auto_now_add=True)),
                ("algorithm_version", models.CharField(max_length=64)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="generated_symptom_checklists",
                        to="api.user",
                    ),
                ),
            ],
            options={"ordering": ["-local_date", "-generated_at"]},
        ),
        migrations.CreateModel(
            name="GeneratedSymptomChecklistItem",
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
                ("symptom_id_snapshot", models.PositiveBigIntegerField()),
                ("symptom_code", models.CharField(max_length=255)),
                ("display_name", models.CharField(max_length=255)),
                ("position", models.PositiveSmallIntegerField()),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("reported", "Reported by user"),
                            ("not_reported", "Not reported by user"),
                            ("not_answered", "Not answered"),
                        ],
                        default="not_answered",
                        max_length=16,
                    ),
                ),
                (
                    "checklist",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="items",
                        to="api.generatedsymptomchecklist",
                    ),
                ),
            ],
            options={"ordering": ["position"]},
        ),
        migrations.CreateModel(
            name="SymptomChecklistResponse",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                (
                    "checklist_type",
                    models.CharField(
                        choices=[("mommy", "Mommy"), ("baby", "Baby")],
                        max_length=16,
                    ),
                ),
                ("local_date", models.DateField()),
                ("recorded_at", models.DateTimeField()),
                ("submitted_at", models.DateTimeField(auto_now_add=True)),
                ("reported_symptom_ids", models.JSONField(default=list)),
                ("reported_symptom_codes", models.JSONField(default=list)),
                (
                    "checklist",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="responses",
                        to="api.generatedsymptomchecklist",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="symptom_checklist_responses",
                        to="api.user",
                    ),
                ),
            ],
            options={"ordering": ["-submitted_at"]},
        ),
        migrations.CreateModel(
            name="SymptomChecklistResponseItem",
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
                ("symptom_code", models.CharField(max_length=255)),
                ("display_name", models.CharField(max_length=255)),
                ("position", models.PositiveSmallIntegerField()),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("reported", "Reported by user"),
                            ("not_reported", "Not reported by user"),
                            ("not_answered", "Not answered"),
                        ],
                        max_length=16,
                    ),
                ),
                (
                    "response",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="items",
                        to="api.symptomchecklistresponse",
                    ),
                ),
            ],
            options={"ordering": ["position"]},
        ),
        migrations.AddConstraint(
            model_name="generatedsymptomchecklist",
            constraint=models.UniqueConstraint(
                fields=("user", "checklist_type", "local_date"),
                name="unique_daily_symptom_checklist",
            ),
        ),
        migrations.AddIndex(
            model_name="generatedsymptomchecklist",
            index=models.Index(
                fields=["user", "checklist_type", "local_date"],
                name="symptom_checklist_lookup_idx",
            ),
        ),
        migrations.AddConstraint(
            model_name="generatedsymptomchecklistitem",
            constraint=models.UniqueConstraint(
                fields=("checklist", "position"),
                name="unique_symptom_checklist_position",
            ),
        ),
        migrations.AddConstraint(
            model_name="generatedsymptomchecklistitem",
            constraint=models.UniqueConstraint(
                fields=("checklist", "symptom_code"),
                name="unique_symptom_checklist_code",
            ),
        ),
        migrations.AddIndex(
            model_name="symptomchecklistresponse",
            index=models.Index(
                fields=["user", "checklist_type", "local_date"],
                name="symptom_response_lookup_idx",
            ),
        ),
        migrations.AddConstraint(
            model_name="symptomchecklistresponseitem",
            constraint=models.UniqueConstraint(
                fields=("response", "symptom_code"),
                name="unique_symptom_response_code",
            ),
        ),
    ]
