# authentication.py (внутри api/)

from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model

UserModel = get_user_model()


class EmailBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        try:
            user = UserModel.objects.get(email=username)
            # if request is not None:
            #     from django.contrib.auth import login

            #     login(request, user)
        except UserModel.DoesNotExist:
            return None

        if user.check_password(password):
            return user
        return None
