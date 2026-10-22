import logging
from uuid import UUID

from django.db import transaction
from django.db.models import Count
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .auth import participant_from_request
from .auth_views import BEARER_AUTH
from .models import Activity, Enrollment
from .serializers import (
    ActivityOutSerializer,
    ActivityV2OutSerializer,
    EnrollmentOutSerializer,
    ErrorOutSerializer,
)

logger = logging.getLogger("app.activities")

ACTIVITY_NOT_FOUND = {
    "code": "activity_not_found",
    "message": "La actividad no existe.",
}
INVALID_IDENTITY = {
    "code": "authentication_required",
    "message": "Falta un access token válido (Authorization: Bearer ...).",
}
CAPACITY_EXHAUSTED = {
    "code": "capacity_exhausted",
    "message": "No hay cupos disponibles.",
}
INVALID_REQUEST = {
    "code": "invalid_request",
    "message": "PUT no recibe un body en esta versión.",
}
REQUEST_NOT_VALID = {
    "code": "invalid_request",
    "message": "Los parámetros del request no son válidos.",
}

ACTIVITY_ID_PARAMETER = OpenApiParameter(
    name="activity_id",
    type=OpenApiTypes.UUID,
    location=OpenApiParameter.PATH,
    required=True,
    description="Identificador único de la actividad.",
)

METHOD_NOT_ALLOWED = OpenApiResponse(description="Método no permitido.")
NO_CONTENT = OpenApiResponse(description="Inscripción cancelada.")


def parse_activity_id(activity_id):
    try:
        return UUID(activity_id)
    except (TypeError, ValueError):
        return None


class ActivityListView(APIView):
    serializer_class = ActivityOutSerializer

    @extend_schema(
        operation_id="listActivities",
        summary="Listar actividades",
        description="Devuelve todas las actividades ordenadas por fecha de inicio.",
        tags=["Activities"],
        auth=[],
        responses={200: ActivityOutSerializer(many=True), 405: METHOD_NOT_ALLOWED},
    )
    def get(self, request):
        logger.info(
            "Listando actividades",
            extra={
                "method": request.method,
                "path": request.path,
                "event": "list_activities",
                "correlation_id": getattr(request, "correlation_id", None),
            },
        )
        activities = Activity.objects.annotate(enrolled_count=Count("enrollments")).order_by("starts_at")
        serializer = self.serializer_class(activities, many=True)
        return Response(serializer.data)


class ActivityDetailView(APIView):
    serializer_class = ActivityOutSerializer

    @extend_schema(
        operation_id="getActivity",
        summary="Consultar una actividad",
        description="Recupera una actividad concreta a partir de su UUID.",
        tags=["Activities"],
        parameters=[ACTIVITY_ID_PARAMETER],
        auth=[],
        responses={200: ActivityOutSerializer, 400: ErrorOutSerializer, 404: ErrorOutSerializer, 405: METHOD_NOT_ALLOWED},
    )
    def get(self, request, activity_id):
        activity_id = parse_activity_id(activity_id)
        if activity_id is None:
            return Response(REQUEST_NOT_VALID, status=status.HTTP_400_BAD_REQUEST)
        try:
            activity = Activity.objects.annotate(enrolled_count=Count("enrollments")).get(id=activity_id)
        except Activity.DoesNotExist:
            return Response(ACTIVITY_NOT_FOUND, status=status.HTTP_404_NOT_FOUND)
        return Response(self.serializer_class(activity).data)


class ActivityListV2View(ActivityListView):
    serializer_class = ActivityV2OutSerializer

    @extend_schema(
        operation_id="listActivitiesV2",
        summary="Listar actividades (v2)",
        description="Representación v2: capacity y available_slots agrupados en `availability`.",
        tags=["Activities"],
        auth=[],
        responses={200: ActivityV2OutSerializer(many=True), 405: METHOD_NOT_ALLOWED},
    )
    def get(self, request):
        return super().get(request)


class ActivityDetailV2View(ActivityDetailView):
    serializer_class = ActivityV2OutSerializer

    @extend_schema(
        operation_id="getActivityV2",
        summary="Consultar una actividad (v2)",
        description="Recupera una actividad con la representación v2 (availability anidada).",
        tags=["Activities"],
        parameters=[ACTIVITY_ID_PARAMETER],
        auth=[],
        responses={200: ActivityV2OutSerializer, 400: ErrorOutSerializer, 404: ErrorOutSerializer, 405: METHOD_NOT_ALLOWED},
    )
    def get(self, request, activity_id):
        return super().get(request, activity_id)


class EnrollmentListView(APIView):
    @extend_schema(
        operation_id="listMyEnrollments",
        summary="Listar mis inscripciones",
        description=(
            "Lista las inscripciones del participante identificado por el access Bearer. "
            "Devuelve una colección vacía si no tiene inscripciones."
        ),
        tags=["Enrollments"],
        auth=BEARER_AUTH,
        responses={200: EnrollmentOutSerializer(many=True), 401: ErrorOutSerializer, 405: METHOD_NOT_ALLOWED},
    )
    def get(self, request):
        participant = participant_from_request(request)
        if participant is None:
            return Response(INVALID_IDENTITY, status=status.HTTP_401_UNAUTHORIZED)

        enrollments = Enrollment.objects.filter(participant=participant).order_by("enrolled_at")
        serializer = EnrollmentOutSerializer(enrollments, many=True)
        return Response(serializer.data)


class EnrollmentDetailView(APIView):
    def get_participant(self, request):
        return participant_from_request(request)

    @extend_schema(
        operation_id="putMyEnrollment",
        summary="Inscribirme en una actividad",
        description=(
            "Crea una inscripción sin body. Responde 201 si la crea y 200 con la "
            "inscripción existente si se repite el mismo PUT."
        ),
        tags=["Enrollments"],
        parameters=[ACTIVITY_ID_PARAMETER],
        auth=BEARER_AUTH,
        request=None,
        responses={
            200: EnrollmentOutSerializer,
            201: EnrollmentOutSerializer,
            400: ErrorOutSerializer,
            401: ErrorOutSerializer,
            404: ErrorOutSerializer,
            409: ErrorOutSerializer,
            405: METHOD_NOT_ALLOWED,
        },
    )
    def put(self, request, activity_id):
        activity_id = parse_activity_id(activity_id)
        if activity_id is None:
            logger.info(
                "activity_id=%s is invalid",
                activity_id,
                extra={
                    "event": "request_invalid_request",
                    "result": "invalid_activity_id",
                    "method": request.method,
                    "path": request.path,
                    "correlation_id": request.correlation_id,
                },
            )
            return Response(REQUEST_NOT_VALID, status=status.HTTP_400_BAD_REQUEST)

        participant = self.get_participant(request)
        if participant is None:
            return Response(INVALID_IDENTITY, status=status.HTTP_401_UNAUTHORIZED)
        if request.body:
            return Response(INVALID_REQUEST, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            try:
                activity = Activity.objects.select_for_update().get(id=activity_id)
            except Activity.DoesNotExist:
                return Response(ACTIVITY_NOT_FOUND, status=status.HTTP_404_NOT_FOUND)

            common_fields = {
                "method": request.method,
                "path": request.path,
                "correlation_id": request.correlation_id,
                "activity_id": str(activity.id),
                "participant_id": str(participant.id),
            }

            enrollment = Enrollment.objects.filter(participant=participant, activity=activity).first()
            if enrollment is not None:
                logger.info("enrollment_reused", extra={"event": "enrollment_reused", "result": "reused", **common_fields})
                return Response(EnrollmentOutSerializer(enrollment).data)

            if activity.enrollments.count() >= activity.capacity:
                logger.warning("enrollment_rejected", extra={"event": "enrollment_rejected", "result": "capacity_exhausted", **common_fields})
                return Response(CAPACITY_EXHAUSTED, status=status.HTTP_409_CONFLICT)

            enrollment = Enrollment.objects.create(participant=participant, activity=activity)
            logger.info("enrollment_created", extra={"event": "enrollment_created", "result": "created", **common_fields})

        return Response(EnrollmentOutSerializer(enrollment).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        operation_id="deleteMyEnrollment",
        summary="Cancelar mi inscripción",
        description=(
            "Elimina la inscripción del participante y libera el cupo. "
            "Idempotente: responde siempre 204 si la actividad existe."
        ),
        tags=["Enrollments"],
        parameters=[ACTIVITY_ID_PARAMETER],
        auth=BEARER_AUTH,
        responses={
            204: NO_CONTENT,
            400: ErrorOutSerializer,
            401: ErrorOutSerializer,
            404: ErrorOutSerializer,
            405: METHOD_NOT_ALLOWED,
        },
    )
    def delete(self, request, activity_id):
        activity_id = parse_activity_id(activity_id)
        if activity_id is None:
            return Response(REQUEST_NOT_VALID, status=status.HTTP_400_BAD_REQUEST)

        participant = self.get_participant(request)
        if participant is None:
            return Response(INVALID_IDENTITY, status=status.HTTP_401_UNAUTHORIZED)

        try:
            activity = Activity.objects.get(id=activity_id)
        except Activity.DoesNotExist:
            return Response(ACTIVITY_NOT_FOUND, status=status.HTTP_404_NOT_FOUND)

        deleted_count, _ = Enrollment.objects.filter(participant=participant, activity=activity).delete()
        logger.info(
            "enrollment_cancelled",
            extra={
                "event": "enrollment_cancelled",
                "result": "cancelled" if deleted_count else "not_found",
                "method": request.method,
                "path": request.path,
                "correlation_id": request.correlation_id,
                "activity_id": str(activity.id),
                "participant_id": str(participant.id),
            },
        )
        return Response(status=status.HTTP_204_NO_CONTENT)
