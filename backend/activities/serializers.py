from rest_framework import serializers

class ActivityOutSerializer(serializers.Serializer):
    id = serializers.UUIDField(help_text="Identificador único de la actividad.")
    title = serializers.CharField(help_text="Nombre visible de la actividad.")
    starts_at = serializers.DateTimeField(
        help_text="Fecha y hora de inicio en formato ISO 8601."
    )
    capacity = serializers.IntegerField(
        min_value=0,
        help_text="Cantidad máxima de participantes.",
    )
    available_slots = serializers.SerializerMethodField(
        help_text="Cupos disponibles según las inscripciones persistidas."
    )

    def get_available_slots(self, activity) -> int:
        return compute_available_slots(activity)

class EnrollmentOutSerializer(serializers.Serializer):
    activity_id = serializers.UUIDField(
        help_text="Actividad en la que se inscribió."
    )
    # participant_id = serializers.UUIDField(
    #     help_text="Participante de la inscripción."
    # )
    enrolled_at = serializers.DateTimeField(
        help_text="Fecha y hora de inscripción en formato ISO 8601."
    )


class ErrorOutSerializer(serializers.Serializer):
    code = serializers.CharField(
        help_text="Código estable y legible por clientes."
    )
    message = serializers.CharField(help_text="Descripción del error.")

def compute_available_slots(activity) -> int:
    enrolled_count = getattr(activity, "enrolled_count", None)
    if enrolled_count is None:
        enrolled_count = activity.enrollments.count()
    return max(activity.capacity - enrolled_count, 0)

class ActivityAvailabilityOutSerializer(serializers.Serializer):
    capacity = serializers.IntegerField(
        min_value=0, help_text="Cantidad máxima de participantes."
    )
    available_slots = serializers.SerializerMethodField(
        help_text="Cupos disponibles según las inscripciones persistidas."
    )

    def get_available_slots(self, activity) -> int:
        return compute_available_slots(activity)


class ActivityV2OutSerializer(serializers.Serializer):
    id = serializers.UUIDField(help_text="Identificador único de la actividad.")
    title = serializers.CharField(help_text="Nombre visible de la actividad.")
    starts_at = serializers.DateTimeField(
        help_text="Fecha y hora de inicio en formato ISO 8601."
    )
    availability = ActivityAvailabilityOutSerializer(
        source="*",
        help_text="Información agrupada de capacidad y disponibilidad.",
    )