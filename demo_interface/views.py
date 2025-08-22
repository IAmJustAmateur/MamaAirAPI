from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import get_object_or_404, redirect, render
from django.shortcuts import render, redirect
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from .forms import *
from django.shortcuts import get_object_or_404
from api.models import Movement, User, Exposure
import random
from datetime import datetime, timedelta
from io import TextIOWrapper
import csv

from .forms import UserLifeStyleForm
from .utils import generate_plausible_movements_24h

from django.contrib.auth.decorators import user_passes_test


def staff_required(user):
    return user.is_staff  # tweak if you use a different permission scheme


@user_passes_test(lambda u: u.is_authenticated and u.is_staff, login_url="/login/")
def user_list(request):
    users = User.objects.exclude(is_superuser=True).order_by("email")
    return render(request, "demo_interface/user_list.html", {"users": users})


@user_passes_test(lambda u: u.is_authenticated and u.is_staff, login_url="/login/")
def create_user(request):
    if request.method == "POST":
        user_form = UserCreateForm(request.POST)
        lifestyle_form = UserLifeStyleForm(request.POST)
        if user_form.is_valid() and lifestyle_form.is_valid():
            user = user_form.save()
            lifestyle = lifestyle_form.save(commit=False)
            lifestyle.user = user
            lifestyle.save()
            messages.success(request, "User created.")
            return redirect("user_list")
    else:
        user_form = UserCreateForm()
        lifestyle_form = UserLifeStyleForm()
    return render(
        request,
        "demo_interface/create_user.html",
        {
            "user_form": user_form,
            "lifestyle_form": lifestyle_form,
        },
    )


# views.py
@user_passes_test(lambda u: u.is_authenticated and u.is_staff, login_url="/login/")
def edit_user(request, user_id):
    user = get_object_or_404(User, id=user_id)
    lifestyle, _ = UserLifeStyle.objects.get_or_create(user=user)

    if request.method == "POST":
        user_form = UserEditForm(request.POST, instance=user)
        lifestyle_form = UserLifeStyleForm(request.POST, instance=lifestyle)
        if user_form.is_valid() and lifestyle_form.is_valid():
            user = user_form.save()
            lifestyle = lifestyle_form.save(commit=False)
            lifestyle.user = user
            lifestyle.save()
            messages.success(request, "User updated.")
            return redirect("user_list")
    else:
        user_form = UserEditForm(instance=user)
        user_form.fields["password"].required = False
        lifestyle_form = UserLifeStyleForm(instance=lifestyle)

    # risks
    try:
        user_risks_dict = user.calculate_risk_factors()
    except Exception as e:
        user_risks_dict = {}
        messages.warning(request, f"Risk calc error: {e}")

    user_risks = []
    for name, data in user_risks_dict.items():
        user_risks.append(
            {
                "name": name,
                "risk_value": data.get("risk_value", 1),
                "priority": data.get("priority", 9999),
            }
        )
    user_risks.sort(key=lambda r: (r["priority"], -float(r["risk_value"] or 0)))

    # mommy symptoms
    try:
        mommy_symptoms_for_checking = user.get_mommy_symptoms_for_checking()
    except Exception as e:
        mommy_symptoms_for_checking = []
        messages.warning(request, f"Symptoms selection error: {e}")

    # exposure history -> подготовим строки с поллютантами
    exposures_qs = Exposure.objects.filter(user=user).order_by("-timestamp")
    exposure_rows = []
    for exp in exposures_qs:
        p = exp.pollutants or {}
        exposure_rows.append(
            {
                "date": exp.timestamp,
                "exposure": exp.exposure_level,
                "pm25": p.get("pm25"),
                "no2": p.get("no2"),
                "so2": p.get("so2"),
                "o3": p.get("o3"),
                "co": p.get("co"),
            }
        )

    return render(
        request,
        "demo_interface/edit_user.html",
        {
            "user_form": user_form,
            "lifestyle_form": lifestyle_form,
            "user_obj": user,
            "user_risks": user_risks,
            "mommy_symptoms_for_checking": mommy_symptoms_for_checking,
            "exposure_rows": exposure_rows,  # <- передаём в шаблон
        },
    )


@user_passes_test(lambda u: u.is_authenticated and u.is_staff, login_url="/login/")
def perform_actions(request):
    mommy_form = MommySymptomForm()
    baby_form = BabySymptomForm()
    movement_upload_form = MovementUploadForm()
    selected_user = None

    # 1. GET-запрос для выбора пользователя
    selected_user_id = request.GET.get("selected_user") or request.POST.get(
        "selected_user"
    )
    if selected_user_id:
        try:
            selected_user = User.objects.get(id=selected_user_id)
        except User.DoesNotExist:
            messages.error(request, "Invalid user selected.")
            return redirect("perform_actions")

    # 2. POST-запросы на действия
    if request.method == "POST":
        if not selected_user:
            messages.error(request, "No user selected.")
            return redirect("perform_actions")

        if "submit_mommy" in request.POST:
            mommy_form = MommySymptomForm(request.POST)
            if mommy_form.is_valid():
                mommy = mommy_form.save(commit=False)
                mommy.user = selected_user
                mommy.save()
                messages.success(request, "Mommy symptom added.")

        elif "submit_baby" in request.POST:
            baby_form = BabySymptomForm(request.POST)
            if baby_form.is_valid():
                baby = baby_form.save(commit=False)
                baby.user = selected_user
                baby.save()
                messages.success(request, "Baby symptom added.")

        elif "upload_movements" in request.POST:
            movement_upload_form = MovementUploadForm(request.POST, request.FILES)
            if movement_upload_form.is_valid():
                uploaded_file = movement_upload_form.cleaned_data.get("file")
                if uploaded_file:
                    file = TextIOWrapper(uploaded_file.file, encoding="utf-8")
                    reader = csv.DictReader(file)
                    for row in reader:
                        Movement.objects.create(
                            user=selected_user,
                            latitude=float(row["latitude"]),
                            longitude=float(row["longitude"]),
                            timestamp=datetime.fromisoformat(row["timestamp"]),
                        )
                    messages.success(request, "Movement data uploaded.")
                else:
                    messages.info(request, "No file uploaded.")

        elif "generate_movements" in request.POST:
            generate_plausible_movements_24h(selected_user)
            messages.success(request, "Random movements generated.")

    return render(
        request,
        "demo_interface/perform_actions.html",
        {
            "mommy_form": mommy_form,
            "baby_form": baby_form,
            "movement_upload_form": movement_upload_form,
            "users": User.objects.all().exclude(is_staff=True),
            "selected_user": selected_user,
        },
    )


@login_required
@user_passes_test(staff_required)
def edit_lifestyle(request, user_id):
    """
    Create or update a user's lifestyle. One-to-one is created on the fly if missing.
    """
    target_user = get_object_or_404(User, pk=user_id)
    lifestyle, _created = UserLifeStyle.objects.get_or_create(user=target_user)

    if request.method == "POST":
        form = UserLifeStyleForm(request.POST, instance=lifestyle)
        if form.is_valid():
            form.save()
            messages.success(request, "Lifestyle saved successfully.")
            return redirect("edit_lifestyle", user_id=target_user.id)
        messages.error(request, "Please correct the errors below.")
    else:
        form = UserLifeStyleForm(instance=lifestyle)

    return render(
        request,
        "demo_interface/edit_lifestyle.html",
        {"form": form, "target_user": target_user},
    )
