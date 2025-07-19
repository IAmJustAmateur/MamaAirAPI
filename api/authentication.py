# authentication.py (внутри api/)

from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model

UserModel = get_user_model()
import logging

logger = logging.getLogger(__name__)


class EmailBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        logger.info(f"Authenticating user with email: {username}")
        try:
            user = UserModel.objects.get(email=username)
            logger.info(f"User found: {user}")
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
        logger.info(f"Retrieving user with ID: {user_id}")
        try:
            user = UserModel.objects.get(pk=user_id)
            logger.info(f"User retrieved: {user}")
            return user
        except UserModel.DoesNotExist:
            return None
