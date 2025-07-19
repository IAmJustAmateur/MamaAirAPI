# authentication.py (внутри api/)

from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model

UserModel = get_user_model()
import logging

logger = logging.getLogger(__name__)


class EmailBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        try:
            user = UserModel.objects.get(email=username)
            # if request is not None:
            #     from django.contrib.auth import login

            #     login(request, user)
        except UserModel.DoesNotExist:
            logger.info(f"User with email {username} does not exist")
            return None

        if user.check_password(password):
            logger.info(f"User authenticated: {user}")
            return user

        return None

    def get_user(self, user_id):
        try:
            return UserModel.objects.get(pk=user_id)
        except UserModel.DoesNotExist:
            return None
