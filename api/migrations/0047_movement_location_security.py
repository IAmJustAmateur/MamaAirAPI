from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0046_user_avatar"),
    ]

    operations = [
        migrations.AddField(
            model_name="movement",
            name="h3_cell",
            field=models.CharField(
                blank=True,
                db_index=True,
                editable=False,
                max_length=15,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="movement",
            name="coordinates_encrypted",
            field=models.BinaryField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="movement",
            name="coordinates_key_version",
            field=models.PositiveSmallIntegerField(
                blank=True,
                editable=False,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="movement",
            name="coordinates_purged_at",
            field=models.DateTimeField(
                blank=True,
                editable=False,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="airexposurelog",
            name="h3_cell",
            field=models.CharField(
                blank=True,
                db_index=True,
                editable=False,
                max_length=15,
                null=True,
            ),
        ),
        migrations.AddIndex(
            model_name="movement",
            index=models.Index(
                fields=["user", "timestamp"],
                name="movement_user_ts_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="movement",
            index=models.Index(
                fields=["user", "h3_cell", "timestamp"],
                name="movement_user_h3_ts_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="airexposurelog",
            index=models.Index(
                fields=["user", "h3_cell", "timestamp"],
                name="airexp_user_h3_ts_idx",
            ),
        ),
    ]
