from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularJSONAPIView, SpectacularSwaggerView

v1_patterns = [path("api/v1/", include("activities.api_urls"))]
v2_patterns = [path("api/v2/", include("activities.api_v2_urls"))]

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include("activities.api_urls")),
    path("api/v2/", include("activities.api_v2_urls")),
    path("", include("activities.urls")),

    path(
        "api/v1/openapi.json",
        SpectacularJSONAPIView.as_view(
            patterns=v1_patterns,
            custom_settings={
                "TITLE": "API de actividades e inscripciones — v1",
                "VERSION": "1.0.0",
            },
        ),
        name="api-schema-v1",
    ),
    path(
        "api/v1/docs",
        SpectacularSwaggerView.as_view(url_name="api-schema-v1"),
        name="api-docs-v1",
    ),

    path(
        "api/v2/openapi.json",
        SpectacularJSONAPIView.as_view(
            patterns=v2_patterns,
            custom_settings={
                "TITLE": "API de actividades e inscripciones — v2",
                "VERSION": "2.0.0",
            },
        ),
        name="api-schema-v2",
    ),
    path(
        "api/v2/docs",
        SpectacularSwaggerView.as_view(url_name="api-schema-v2"),
        name="api-docs-v2",
    ),
]