# demo_interface/views_api.py
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework import status
from rest_framework.authentication import (
    SessionAuthentication,
    TokenAuthentication,
)
from rest_framework.authentication import SessionAuthentication, TokenAuthentication
from rest_framework_simplejwt.authentication import JWTAuthentication  # <-- добавь эт

from .serializers import DemoUserCreateSerializer, DemoUserLifeStyleSerializer


@api_view(["POST"])
@authentication_classes(
    [SessionAuthentication, TokenAuthentication, JWTAuthentication]
)  # при необходимости добавь JWT
@permission_classes([IsAdminUser])  # только staff
def api_create_user(request):
    """
    Создать пользователя (только для staff).
    Принимает JSON полей DemoUserCreateSerializer.
    """
    ser = DemoUserCreateSerializer(data=request.data)
    if ser.is_valid():
        user = ser.save()
        return Response(
            {"id": user.id, "email": user.email}, status=status.HTTP_201_CREATED
        )
    return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@authentication_classes([SessionAuthentication, TokenAuthentication, JWTAuthentication])
@permission_classes([IsAdminUser])
def api_create_or_update_lifestyle(request):
    """
    Создать/обновить Lifestyle (OneToOne) по user (PK).
    """
    ser = DemoUserLifeStyleSerializer(data=request.data)
    if ser.is_valid():
        ls = ser.save()
        return Response(
            {"id": ls.id, "user": ls.user_id}, status=status.HTTP_201_CREATED
        )
    return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)
