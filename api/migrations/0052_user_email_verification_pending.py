from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("api", "0051_mental_recommendation_dimension")]

    operations = [
        migrations.AddField(
            model_name="user",
            name="email_verification_pending",
            field=models.BooleanField(default=False),
        ),
    ]
