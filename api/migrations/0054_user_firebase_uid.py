from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("api", "0053_auditlog")]

    operations = [
        migrations.AddField(
            model_name="user",
            name="firebase_uid",
            field=models.CharField(max_length=128, null=True, blank=True, unique=True),
        ),
    ]
