from django.shortcuts import render, redirect
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from .forms import *
from django.shortcuts import get_object_or_404
from api.models import Movement
import random
from datetime import datetime, timedelta
from io import TextIOWrapper
import csv

from django.contrib.auth.decorators import user_passes_test


@user_passes_test(lambda u: u.is_authenticated and u.is_staff, login_url="/login/")
def user_list(request):
    users = User.objects.exclude(id=request.user.id)
    return render(request, "demo_interface/user_list.html", {"users": users})


@user_passes_test(lambda u: u.is_authenticated and u.is_staff, login_url="/login/")
def create_user(request):
    if request.method == "POST":
        user_form = UserCreateForm(request.POST)
        lifestyle_form = UserLifestyleForm(request.POST)
        if user_form.is_valid() and lifestyle_form.is_valid():
            user = user_form.save()
            lifestyle = lifestyle_form.save(commit=False)
            lifestyle.user = user
            lifestyle.save()
            messages.success(request, "User created.")
            return redirect("user_list")
    else:
        user_form = UserCreateForm()
        lifestyle_form = UserLifestyleForm()
    return render(
        request,
        "demo_interface/create_user.html",
        {
            "user_form": user_form,
            "lifestyle_form": lifestyle_form,
        },
    )


@user_passes_test(lambda u: u.is_authenticated and u.is_staff, login_url="/login/")
def edit_user(request, user_id):
    user = get_object_or_404(User, id=user_id)
    lifestyle, _ = UserLifeStyle.objects.get_or_create(user=user)
    if request.method == "POST":
        user_form = UserEditForm(request.POST, instance=user)
        lifestyle_form = UserLifestyleForm(request.POST, instance=lifestyle)
        if user_form.is_valid() and lifestyle_form.is_valid():
            user = user_form.save()
            lifestyle = lifestyle_form.save(commit=False)
            lifestyle.user = user
            lifestyle.save()
            messages.success(request, "User updated.")
            return redirect("user_list")
    else:
        user_form = UserEditForm(instance=user)
        user_form.fields["password"].required = False  # don't force password update
        lifestyle_form = UserLifestyleForm(instance=lifestyle)
    return render(
        request,
        "demo_interface/edit_user.html",
        {
            "user_form": user_form,
            "lifestyle_form": lifestyle_form,
            "user_obj": user,
        },
    )


@user_passes_test(lambda u: u.is_authenticated and u.is_staff, login_url="/login/")
def perform_actions(request):
    mommy_form = MommySymptomForm()
    baby_form = BabySymptomForm()
    movement_upload_form = MovementUploadForm()

    if request.method == "POST":
        if "submit_mommy" in request.POST:
            mommy_form = MommySymptomForm(request.POST)
            if mommy_form.is_valid():
                mommy_form.save()
                messages.success(request, "Mommy symptom added.")

        elif "submit_baby" in request.POST:
            baby_form = BabySymptomForm(request.POST)
            if baby_form.is_valid():
                baby_form.save()
                messages.success(request, "Baby symptom added.")

        elif "upload_movements" in request.POST:
            movement_upload_form = MovementUploadForm(request.POST, request.FILES)
            if movement_upload_form.is_valid():
                user = movement_upload_form.cleaned_data["user"]
                file = TextIOWrapper(request.FILES["file"].file, encoding="utf-8")
                reader = csv.DictReader(file)
                for row in reader:
                    Movement.objects.create(
                        user=user,
                        latitude=float(row["latitude"]),
                        longitude=float(row["longitude"]),
                        timestamp=datetime.fromisoformat(row["timestamp"]),
                    )
                messages.success(request, "Movement data uploaded.")

        elif "generate_movements" in request.POST:
            user_id = request.POST.get("generate_user")
            user = User.objects.get(pk=user_id)
            for i in range(10):
                Movement.objects.create(
                    user=user,
                    latitude=random.uniform(-90, 90),
                    longitude=random.uniform(-180, 180),
                    timestamp=datetime.now() - timedelta(minutes=i * 10),
                )
            messages.success(request, "Random movements generated.")

    return render(
        request,
        "demo_interface/perform_actions.html",
        {
            "mommy_form": mommy_form,
            "baby_form": baby_form,
            "movement_upload_form": movement_upload_form,
            "users": User.objects.all(),
        },
    )
