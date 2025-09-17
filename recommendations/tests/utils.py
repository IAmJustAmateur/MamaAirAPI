# tests/utils.py  (или рядом в каждом тестовом файле)
from django.contrib.auth import get_user_model

User = get_user_model()


def make_user_with_bmi(
    email: str, password: str = "x", *, bmi: float, height_cm: int = 170, **extra
):
    """Создаёт пользователя с заданным BMI, вычисляя weight_pre_pregnancy под рост."""
    h2 = (height_cm / 100.0) ** 2
    weight = round(bmi * h2, 1)  # кг, одно десятичное — достаточно
    return User.objects.create_user(
        email=email,
        password=password,
        height=height_cm,
        weight_pre_pregnancy=weight,
        **extra,
    )
