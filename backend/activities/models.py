import uuid

from django.conf import settings
from django.db import models


class Activity(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=160)
    starts_at = models.DateTimeField()
    capacity = models.PositiveIntegerField()

    class Meta:
        ordering = ("starts_at",)
        verbose_name_plural = "activities"

    def __str__(self):
        return self.title


class Participant(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=160)
    # Cuenta de Django que puede actuar como este participante (login con JWT).
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="participant",
    )

    class Meta:
        verbose_name_plural = "participants"

    def __str__(self):
        return self.name


class Enrollment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    participant = models.ForeignKey(
        Participant,
        on_delete=models.CASCADE,
        related_name="enrollments",
    )
    activity = models.ForeignKey(
        Activity,
        on_delete=models.CASCADE,
        related_name="enrollments",
    )
    enrolled_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "enrollments"
        constraints = [
            models.UniqueConstraint(
                fields=("participant", "activity"),
                name="unique_enrollment",
            )
        ]

    def __str__(self):
        return f"{self.participant} -> {self.activity}"


class RefreshToken(models.Model):
    """Refresh opaco: en la base solo se guarda su hash, nunca el valor original."""

    digest = models.CharField(max_length=64, unique=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"refresh de {self.user_id} (revocado: {self.revoked_at is not None})"
