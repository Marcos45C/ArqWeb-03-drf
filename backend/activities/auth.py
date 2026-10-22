"""Tokens del Hito 2: access JWT firmado (stateless) y refresh opaco rotativo (en base)."""
import hashlib
import secrets
from datetime import timedelta

import jwt
from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone

from .models import Participant, RefreshToken


def digest(value):
    """SHA-256 del refresh: la base nunca guarda el valor original."""
    return hashlib.sha256(value.encode()).hexdigest()


def make_access(user):
    """Access breve y firmado. No se guarda en ningún lado: se valida por firma y vencimiento."""
    now = int(timezone.now().timestamp())
    return jwt.encode(
        {
            "sub": str(user.pk),
            "iat": now,
            "exp": now + settings.ACCESS_SECONDS,
            "iss": settings.JWT_ISSUER,
            "type": "access",
        },
        settings.JWT_SIGNING_KEY,
        algorithm="HS256",
    )


def access_user(token):
    """Devuelve el usuario activo dueño del access, o None si algo no cierra.

    Se fija el algoritmo (HS256), se exigen los claims y se valida emisor y
    vencimiento. Un JWT bien firmado pero con claims raros también da None.
    """
    try:
        claims = jwt.decode(
            token,
            settings.JWT_SIGNING_KEY,
            algorithms=["HS256"],
            issuer=settings.JWT_ISSUER,
            options={"require": ["sub", "iat", "exp", "iss", "type"]},
        )
    except jwt.PyJWTError:
        return None
    if claims.get("type") != "access":
        return None
    subject = claims["sub"]
    if not isinstance(subject, str) or not subject.isascii() or not subject.isdecimal() or len(subject) > 18:
        return None
    return get_user_model().objects.filter(pk=int(subject), is_active=True).first()


def bearer_token(request):
    parts = request.headers.get("Authorization", "").split()
    return parts[1] if len(parts) == 2 and parts[0].lower() == "bearer" else None


def participant_from_request(request):
    """Participante identificado por el access Bearer; None si falta o es inválido.

    Es la ÚNICA forma de saber quién opera: el cliente no puede elegir a quién
    inscribir mandando un id. Una cookie refresh por sí sola no autentica nada.
    """
    token = bearer_token(request)
    user = access_user(token) if token else None
    if user is None:
        return None
    return Participant.objects.filter(user=user).first()


def issue_refresh(user):
    """Crea un refresh aleatorio de alta entropía y guarda solo su hash."""
    value = secrets.token_urlsafe(32)
    RefreshToken.objects.create(
        digest=digest(value),
        user=user,
        expires_at=timezone.now() + timedelta(seconds=settings.REFRESH_SECONDS),
    )
    return value
