"""Login, refresh, logout y perfil. Errores con la forma estable {code, message}."""
import json
import logging

from django.conf import settings
from django.contrib.auth import authenticate
from django.db import transaction
from django.http import HttpResponse
from django.utils import timezone
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .auth import digest, issue_refresh, make_access, participant_from_request
from .models import Participant, RefreshToken
from .serializers import ErrorOutSerializer

logger = logging.getLogger("app.auth")

BEARER_AUTH = [{"bearerAuth": []}]

INVALID_REQUEST = {"code": "invalid_request", "message": "Ingresá email y contraseña."}
INVALID_CREDENTIALS = {"code": "invalid_credentials", "message": "Email o contraseña incorrectos."}
INVALID_REFRESH = {
    "code": "invalid_refresh",
    "message": "La sesión no se pudo renovar. Ingresá nuevamente.",
}
AUTH_REQUIRED = {
    "code": "authentication_required",
    "message": "Falta un access token válido (Authorization: Bearer ...).",
}


class LoginInSerializer(serializers.Serializer):
    email = serializers.CharField()
    password = serializers.CharField()


class TokenOutSerializer(serializers.Serializer):
    access = serializers.CharField(help_text="JWT de acceso, de duración breve.")
    token_type = serializers.CharField(help_text="Siempre Bearer.")
    expires_in = serializers.IntegerField(help_text="Segundos de vida del access.")


class MeOutSerializer(serializers.Serializer):
    id = serializers.UUIDField(help_text="Identificador del participante actual.")
    name = serializers.CharField(help_text="Nombre del participante actual.")


def log_auth(request, event, result, level="info", **extra):
    """Evento estructurado de autenticación. Nunca incluye contraseñas ni tokens."""
    getattr(logger, level)(
        event,
        extra={
            "event": event,
            "result": result,
            "method": request.method,
            "path": request.path,
            "correlation_id": getattr(request, "correlation_id", None),
            **extra,
        },
    )


def token_response(request, user, refresh_value):
    """Access en el JSON; refresh solo en cookie HttpOnly con Path acotado."""
    response = Response(
        {"access": make_access(user), "token_type": "Bearer", "expires_in": settings.ACCESS_SECONDS}
    )
    response["Cache-Control"] = "no-store"
    response.set_cookie(
        settings.REFRESH_COOKIE_NAME,
        refresh_value,
        max_age=settings.REFRESH_SECONDS,
        httponly=True,
        secure=settings.REFRESH_COOKIE_SECURE,
        samesite="Strict",
        path=settings.REFRESH_COOKIE_PATH,
    )
    return response


class LoginView(APIView):
    @extend_schema(
        operation_id="login",
        summary="Iniciar sesión",
        description=(
            "Valida email y contraseña. Devuelve un access JWT breve en el body y "
            "establece el refresh en una cookie HttpOnly."
        ),
        tags=["Auth"],
        request=LoginInSerializer,
        auth=[],
        responses={
            200: TokenOutSerializer,
            400: ErrorOutSerializer,
            401: ErrorOutSerializer,
        },
    )
    def post(self, request):
        try:
            data = json.loads(request.body or b"{}")
        except (ValueError, UnicodeDecodeError):
            data = None
        if not isinstance(data, dict) or not isinstance(data.get("email"), str) or not isinstance(data.get("password"), str):
            return Response(INVALID_REQUEST, status=status.HTTP_400_BAD_REQUEST)

        user = authenticate(request, username=data["email"].strip().lower(), password=data["password"])
        participant = Participant.objects.filter(user=user).first() if user else None
        if participant is None:
            log_auth(request, "login_failed", "invalid_credentials", level="warning")
            return Response(INVALID_CREDENTIALS, status=status.HTTP_401_UNAUTHORIZED)

        log_auth(request, "login_succeeded", "ok", participant_id=str(participant.id))
        return token_response(request, user, issue_refresh(user))


class RefreshView(APIView):
    @extend_schema(
        operation_id="refresh",
        summary="Renovar el access",
        description=(
            "Lee el refresh de la cookie HttpOnly, lo consume (un solo uso) y devuelve "
            "un access nuevo y un refresh nuevo. Reusar un refresh ya consumido da 401."
        ),
        tags=["Auth"],
        request=None,
        auth=[],
        responses={200: TokenOutSerializer, 401: ErrorOutSerializer},
    )
    def post(self, request):
        value = request.COOKIES.get(settings.REFRESH_COOKIE_NAME, "")
        if not value:
            log_auth(request, "refresh_rejected", "missing_cookie", level="warning")
            return Response(INVALID_REFRESH, status=status.HTTP_401_UNAUTHORIZED)

        now = timezone.now()
        with transaction.atomic():
            # UPDATE condicional: solo una petición puede pasar revoked_at de NULL a una
            # fecha, aunque lleguen dos juntas. La segunda obtiene 0 filas y recibe 401.
            consumed = RefreshToken.objects.filter(
                digest=digest(value),
                revoked_at__isnull=True,
                expires_at__gt=now,
                user__is_active=True,
            ).update(revoked_at=now)
            if consumed != 1:
                log_auth(request, "refresh_rejected", "invalid_or_reused", level="warning")
                return Response(INVALID_REFRESH, status=status.HTTP_401_UNAUTHORIZED)
            old = RefreshToken.objects.select_related("user").get(digest=digest(value))
            participant = Participant.objects.filter(user=old.user).first()
            if participant is None:
                return Response(INVALID_REFRESH, status=status.HTTP_401_UNAUTHORIZED)
            new_value = issue_refresh(old.user)

        log_auth(request, "token_refreshed", "ok", participant_id=str(participant.id))
        return token_response(request, old.user, new_value)


class LogoutView(APIView):
    @extend_schema(
        operation_id="logout",
        summary="Cerrar sesión",
        description=(
            "Revoca el refresh de la cookie y la elimina. Idempotente. Un access ya "
            "emitido sigue siendo válido hasta su vencimiento: no hay lista de revocación."
        ),
        tags=["Auth"],
        request=None,
        auth=[],
        responses={204: OpenApiResponse(description="Sesión cerrada.")},
    )
    def post(self, request):
        value = request.COOKIES.get(settings.REFRESH_COOKIE_NAME, "")
        if value:
            RefreshToken.objects.filter(digest=digest(value), revoked_at__isnull=True).update(
                revoked_at=timezone.now()
            )
        log_auth(request, "logout", "ok")
        response = HttpResponse(status=204)
        response["Cache-Control"] = "no-store"
        response.delete_cookie(
            settings.REFRESH_COOKIE_NAME, path=settings.REFRESH_COOKIE_PATH, samesite="Strict"
        )
        return response


class MeView(APIView):
    @extend_schema(
        operation_id="getMe",
        summary="Participante actual",
        description="Devuelve el participante identificado por el access Bearer.",
        tags=["Auth"],
        auth=BEARER_AUTH,
        responses={200: MeOutSerializer, 401: ErrorOutSerializer},
    )
    def get(self, request):
        participant = participant_from_request(request)
        if participant is None:
            return Response(AUTH_REQUIRED, status=status.HTTP_401_UNAUTHORIZED)
        response = Response({"id": participant.id, "name": participant.name})
        response["Cache-Control"] = "no-store"
        return response
