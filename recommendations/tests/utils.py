# tests/utils.py  (или рядом в каждом тестовом файле)
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from zoneinfo import ZoneInfo
from datetime import timedelta

User = get_user_model()


def make_user_with_bmi(
    email: str, password: str = "x", *, bmi: float, height_cm: int = 170, **extra
):
    """Создаёт пользователя с заданным BMI, вычисляя weight_pre_pregnancy под рост."""
    h2 = (height_cm / 100.0) ** 2
    weight = round(bmi * h2, 1)  # кг, одно десятичное — достаточно
    user = User.objects.create_user(
        email=email,
        password=password,
        height=height_cm,
        weight_pre_pregnancy=weight,
        **extra,
    )
    user.set_pregnancy_start_date()  # чтобы был current_week_of_pregnancy
    return user


def _build_movements_csv_many(points=24, step_minutes=5, tz_name="Europe/Warsaw"):
    """
    Делает CSV с N точками, каждые step_minutes, за ~последние 2 часа.
    Возвращает SimpleUploadedFile.
    """
    tz = ZoneInfo(tz_name)
    now_local = timezone.now().astimezone(tz)
    start = now_local.replace(minute=0, second=0, microsecond=0) - timedelta(hours=2)

    rows = ["latitude,longitude,timestamp"]
    lat, lon = 52.2297, 21.0122  # Warsaw
    for i in range(points):
        ts = (start + timedelta(minutes=i * step_minutes)).isoformat(timespec="seconds")
        # лёгкий джиттер, чтобы точки не были идентичны
        jlat = lat + (0.0005 - i * 1e-6)
        jlon = lon + (0.0005 - i * 1e-6)
        rows.append(f"{jlat:.6f},{jlon:.6f},{ts}")
    csv_text = "\n".join(rows) + "\n"
    return SimpleUploadedFile(
        "movements_many.csv",
        csv_text.encode("utf-8"),
        content_type="text/csv",
    )
