from api.models import (
    UserLifeStyle,
    UserMommySymptoms,
    UserBabySymptoms,
    Movement,
    User,
    MommySymptom,
    BabySymptom,
)


def create_defaults():
    email = "mom1@example.com"
    password = "Testpass123!"
    mommy_user = User.objects.create_user(
        email=email,
        password=password,
        name="Mommy",
        date_of_birth="1995-08-02",
        height=170,
        weight_pre_pregnancy=60,
        is_first_pregnancy=True,
        race="caucasian",
        week_of_pregnancy=20,
    )
    UserLifeStyle.objects.create(
        user=mommy_user,
        cooking_method="charcoal",
        diet_type="carnivore",
        work_type="desk",
        average_sleep_hours=7,
        activity_duration_minutes=120,
    )
    mommy_symptom_1 = MommySymptom.objects.first()
    mommy_symptom_2 = MommySymptom.objects.last()
    mommy_symptom_3 = MommySymptom.objects.all()[1]

    baby_symptom_1 = BabySymptom.objects.first()
    baby_symptom_2 = BabySymptom.objects.last()
    baby_symptom_3 = BabySymptom.objects.all()[1]

    return {
        "user": mommy_user,
        "password": password,
        "mommy_symptoms": [mommy_symptom_1, mommy_symptom_2, mommy_symptom_3],
        "baby_symptoms": [baby_symptom_1, baby_symptom_2, baby_symptom_3],
    }
