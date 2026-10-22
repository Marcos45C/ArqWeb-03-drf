"""Pruebas del Hito 2: login, access JWT, refresh rotativo, logout y autorización."""
import json
from datetime import timedelta
from uuid import uuid4

import jwt
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.utils import timezone

from .auth import digest, issue_refresh, make_access
from .models import Activity, Enrollment, Participant, RefreshToken

PASSWORD = "Password123!"


class AuthTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.ada = User.objects.create_user(username="ada@example.com", email="ada@example.com", password=PASSWORD)
        self.grace = User.objects.create_user(username="grace@example.com", email="grace@example.com", password=PASSWORD)
        self.p_ada = Participant.objects.create(name="Ada", user=self.ada)
        self.p_grace = Participant.objects.create(name="Grace", user=self.grace)
        self.activity = Activity.objects.create(title="Taller", starts_at=timezone.now(), capacity=1)
        self.url = f"/api/v1/me/enrollments/{self.activity.id}"
        self.bearer_ada = {"HTTP_AUTHORIZATION": "Bearer " + make_access(self.ada)}
        self.bearer_grace = {"HTTP_AUTHORIZATION": "Bearer " + make_access(self.grace)}

    def post_json(self, path, body=None, client=None):
        return (client or self.client).post(path, json.dumps(body or {}), content_type="application/json")

    def login(self, email="ada@example.com", password=PASSWORD):
        return self.post_json("/api/v1/auth/login", {"email": email, "password": password})

    # ---- login ----
    def test_login_ok_access_in_body_refresh_in_httponly_cookie(self):
        response = self.login()
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["token_type"], "Bearer")
        self.assertEqual(body["expires_in"], settings.ACCESS_SECONDS)
        self.assertNotIn("refresh", body)
        cookie = response.cookies[settings.REFRESH_COOKIE_NAME]
        self.assertTrue(cookie["httponly"])
        self.assertEqual(cookie["path"], "/api/v1/auth/")
        self.assertEqual(cookie["samesite"], "Strict")
        # La base guarda el hash, nunca el valor de la cookie.
        self.assertFalse(RefreshToken.objects.filter(digest=cookie.value).exists())
        self.assertTrue(RefreshToken.objects.filter(digest=digest(cookie.value)).exists())

    def test_login_rejects_wrong_credentials_and_bad_requests(self):
        wrong = self.login(password="otra")
        self.assertEqual(wrong.status_code, 401)
        self.assertEqual(wrong.json()["code"], "invalid_credentials")
        self.assertNotIn(settings.REFRESH_COOKIE_NAME, wrong.cookies)
        self.assertEqual(self.login(email="nadie@example.com").status_code, 401)
        self.assertEqual(self.post_json("/api/v1/auth/login", {"email": []}).status_code, 400)
        self.assertEqual(self.client.post("/api/v1/auth/login", "no es json", content_type="application/json").status_code, 400)

    def test_user_without_participant_cannot_login(self):
        get_user_model().objects.create_user(username="x@example.com", password=PASSWORD)
        self.assertEqual(self.login(email="x@example.com").status_code, 401)

    # ---- access ----
    def test_protected_routes_require_a_valid_bearer(self):
        for method, path in [("get", "/api/v1/me"), ("get", "/api/v1/me/enrollments"), ("put", self.url), ("delete", self.url)]:
            with self.subTest(path=path, method=method):
                response = getattr(self.client, method)(path)
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response.json()["code"], "authentication_required")

    def test_participant_id_header_no_longer_identifies_anyone(self):
        response = self.client.get("/api/v1/me/enrollments", HTTP_X_PARTICIPANT_ID=str(self.p_ada.id))
        self.assertEqual(response.status_code, 401)

    def test_invalid_access_tokens_are_rejected(self):
        now = int(timezone.now().timestamp())
        claims = {"sub": str(self.ada.pk), "iat": now, "exp": now + 60, "iss": settings.JWT_ISSUER, "type": "access"}
        sign = lambda c, key=settings.JWT_SIGNING_KEY, alg="HS256": jwt.encode(c, key, algorithm=alg)
        bad = [
            sign({**claims, "exp": now - 1}),
            sign({**claims, "iss": "otro"}),
            sign({**claims, "type": "refresh"}),
            sign({**claims, "sub": "no-es-un-id"}),
            sign({**claims, "sub": "9" * 100}),
            sign({k: v for k, v in claims.items() if k != "exp"}),
            sign(claims, key="otra-clave-de-al-menos-32-bytes-de-largo!!"),
            sign(claims, key="x" * 64, alg="HS512"),
            "no-es-un-jwt",
        ]
        for token in bad:
            with self.subTest(token=token[:25]):
                response = self.client.get("/api/v1/me", HTTP_AUTHORIZATION="Bearer " + token)
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response.json()["code"], "authentication_required")
        # Un token alterado a mano (otro sub, misma firma) tampoco sirve.
        header, _, signature = make_access(self.ada).split(".")
        forged = jwt.utils.base64url_encode(json.dumps({**claims, "sub": str(self.grace.pk)}).encode()).decode()
        response = self.client.get("/api/v1/me", HTTP_AUTHORIZATION=f"Bearer {header}.{forged}.{signature}")
        self.assertEqual(response.status_code, 401)

    def test_inactive_user_access_is_rejected(self):
        self.ada.is_active = False
        self.ada.save()
        self.assertEqual(self.client.get("/api/v1/me", **self.bearer_ada).status_code, 401)

    def test_me_returns_the_participant_from_the_token(self):
        self.assertEqual(self.client.get("/api/v1/me", **self.bearer_ada).json()["name"], "Ada")
        self.assertEqual(self.client.get("/api/v1/me", **self.bearer_grace).json()["name"], "Grace")

    # ---- refresh ----
    def test_refresh_rotates_and_rejects_reuse(self):
        self.login()
        old = self.client.cookies[settings.REFRESH_COOKIE_NAME].value
        response = self.client.post("/api/v1/auth/refresh")
        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.json())
        new = self.client.cookies[settings.REFRESH_COOKIE_NAME].value
        self.assertNotEqual(new, old)
        self.assertIsNotNone(RefreshToken.objects.get(digest=digest(old)).revoked_at)
        self.client.cookies[settings.REFRESH_COOKIE_NAME] = old
        reuse = self.client.post("/api/v1/auth/refresh")
        self.assertEqual(reuse.status_code, 401)
        self.assertEqual(reuse.json()["code"], "invalid_refresh")

    def test_refresh_without_expired_or_invented_cookie(self):
        self.assertEqual(Client().post("/api/v1/auth/refresh").status_code, 401)
        client = Client()
        client.cookies[settings.REFRESH_COOKIE_NAME] = "inventado"
        self.assertEqual(client.post("/api/v1/auth/refresh").status_code, 401)
        value = issue_refresh(self.ada)
        RefreshToken.objects.filter(digest=digest(value)).update(expires_at=timezone.now() - timedelta(seconds=1))
        client.cookies[settings.REFRESH_COOKIE_NAME] = value
        self.assertEqual(client.post("/api/v1/auth/refresh").status_code, 401)

    def test_refresh_cookie_alone_does_not_authenticate_domain_routes(self):
        self.login()
        self.assertEqual(self.client.get("/api/v1/me/enrollments").status_code, 401)

    def test_refresh_of_inactive_user_is_rejected(self):
        self.login()
        self.ada.is_active = False
        self.ada.save()
        self.assertEqual(self.client.post("/api/v1/auth/refresh").status_code, 401)

    # ---- logout ----
    def test_logout_revokes_refresh_but_issued_access_lives_until_exp(self):
        reply = self.login()
        access = reply.json()["access"]
        old = self.client.cookies[settings.REFRESH_COOKIE_NAME].value
        response = self.client.post("/api/v1/auth/logout")
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.cookies[settings.REFRESH_COOKIE_NAME]["max-age"], 0)
        self.assertIsNotNone(RefreshToken.objects.get(digest=digest(old)).revoked_at)
        # Límite documentado: el access ya emitido sigue funcionando hasta vencer.
        self.assertEqual(self.client.get("/api/v1/me", HTTP_AUTHORIZATION="Bearer " + access).status_code, 200)
        # Pero ya no se puede renovar.
        self.client.cookies[settings.REFRESH_COOKIE_NAME] = old
        self.assertEqual(self.client.post("/api/v1/auth/refresh").status_code, 401)

    def test_logout_without_session_is_idempotent(self):
        self.assertEqual(Client().post("/api/v1/auth/logout").status_code, 204)

    # ---- el contrato del Hito 1 se conserva ----
    def test_enrollment_contract_is_preserved_with_jwt(self):
        first = self.client.put(self.url, **self.bearer_ada)
        self.assertEqual(first.status_code, 201)
        self.assertEqual(set(first.json()), {"activity_id", "enrolled_at"})
        again = self.client.put(self.url, **self.bearer_ada)
        self.assertEqual(again.status_code, 200)
        self.assertEqual(again.json(), first.json())
        self.assertEqual(Enrollment.objects.count(), 1)
        full = self.client.put(self.url, **self.bearer_grace)
        self.assertEqual(full.status_code, 409)
        self.assertEqual(full.json()["code"], "capacity_exhausted")
        self.assertEqual(self.client.put(self.url, "{}", content_type="application/json", **self.bearer_ada).status_code, 400)
        self.assertEqual(self.client.put(f"/api/v1/me/enrollments/{uuid4()}", **self.bearer_ada).json()["code"], "activity_not_found")
        # Cada persona ve solo lo suyo: la identidad sale del token.
        self.assertEqual(len(self.client.get("/api/v1/me/enrollments", **self.bearer_ada).json()), 1)
        self.assertEqual(self.client.get("/api/v1/me/enrollments", **self.bearer_grace).json(), [])
        # Cancelar con otra identidad no toca la inscripción ajena; cancelar es idempotente.
        self.assertEqual(self.client.delete(self.url, **self.bearer_grace).status_code, 204)
        self.assertEqual(Enrollment.objects.count(), 1)
        self.assertEqual(self.client.delete(self.url, **self.bearer_ada).status_code, 204)
        self.assertEqual(self.client.delete(self.url, **self.bearer_ada).status_code, 204)
        self.assertEqual(self.client.put(self.url, **self.bearer_grace).status_code, 201)

    def test_public_routes_stay_public_and_v2_shape_is_kept(self):
        v1 = self.client.get("/api/v1/activities").json()[0]
        self.assertEqual(set(v1), {"id", "title", "starts_at", "capacity", "available_slots"})
        v2 = self.client.get("/api/v2/activities").json()[0]
        self.assertEqual(set(v2), {"id", "title", "starts_at", "availability"})
        self.assertEqual(self.client.put(f"/api/v2/me/enrollments/{self.activity.id}", **self.bearer_ada).status_code, 201)

    def test_correlation_id_header_is_still_returned(self):
        response = self.client.get("/api/v1/me", HTTP_X_CORRELATION_ID="demo-42")
        self.assertEqual(response["X-Correlation-ID"], "demo-42")
