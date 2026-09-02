from django.urls import path

from .views import (
    ActivityDetailV2View,
    ActivityListV2View,
    EnrollmentDetailView,
    EnrollmentListView,
)

urlpatterns = [
    path("activities", ActivityListV2View.as_view(), name="api-activity-list-v2"),
    path(
        "activities/<str:activity_id>",
        ActivityDetailV2View.as_view(),
        name="api-activity-detail-v2",
    ),
    path(
        "me/enrollments",
        EnrollmentListView.as_view(),
        name="api-enrollment-list-v2",
    ),
    path(
        "me/enrollments/<str:activity_id>",
        EnrollmentDetailView.as_view(),
        name="api-enrollment-detail-v2",
    ),
]