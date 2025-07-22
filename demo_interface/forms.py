from django import forms
from django.contrib.auth import get_user_model
from api.models import UserLifeStyle, UserMommySymptoms, UserBabySymptoms, Movement
from django.core.exceptions import ValidationError
import csv
from io import TextIOWrapper

User = get_user_model()


class UserCreateForm(forms.ModelForm):
    password = forms.CharField(required=True, widget=forms.PasswordInput)

    class Meta:
        model = User
        fields = [
            "email",
            "password",
            "name",
            "date_of_birth",
            "height",
            "weight_pre_pregnancy",
        ]

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password"])  # hash password
        if commit:
            user.save()
        return user


class UserEditForm(forms.ModelForm):
    password = forms.CharField(required=False, widget=forms.PasswordInput)

    class Meta:
        model = User
        fields = [
            "email",
            "password",
            "name",
            "date_of_birth",
            "height",
            "weight_pre_pregnancy",
        ]

    def save(self, commit=True):
        user = super().save(commit=False)
        if self.cleaned_data["password"]:
            user.set_password(self.cleaned_data["password"])
        if commit:
            user.save()
        return user


class UserLifestyleForm(forms.ModelForm):
    class Meta:
        model = UserLifeStyle
        exclude = ["user"]


class MommySymptomForm(forms.ModelForm):
    class Meta:
        model = UserMommySymptoms
        fields = ["user", "symptom", "date_recorded"]


class BabySymptomForm(forms.ModelForm):
    class Meta:
        model = UserBabySymptoms
        fields = ["user", "symptom", "date_recorded"]


class MovementUploadForm(forms.Form):
    user = forms.ModelChoiceField(queryset=User.objects.all())
    file = forms.FileField()

    def clean_file(self):
        file = self.cleaned_data["file"]
        try:
            TextIOWrapper(file.file, encoding="utf-8")
        except Exception:
            raise ValidationError("Invalid CSV file")
        return file
