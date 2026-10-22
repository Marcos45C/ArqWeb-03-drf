from django.urls import path

from .auth_views import LoginView, LogoutView, MeView, RefreshView
from .views import (
    ActivityDetailView,
    ActivityListView,
    EnrollmentDetailView,
    EnrollmentListView,
)

urlpatterns = [
    path("auth/login", LoginView.as_view(), name="api-auth-login"),
    path("auth/refresh", RefreshView.as_view(), name="api-auth-refresh"),
    path("auth/logout", LogoutView.as_view(), name="api-auth-logout"),
    path("me", MeView.as_view(), name="api-me"),
    path("activities", ActivityListView.as_view(), name="api-activity-list"),
    path("activities/<str:activity_id>", ActivityDetailView.as_view(), name="api-activity-detail"),
    path("me/enrollments", EnrollmentListView.as_view(), name="api-enrollment-list"),
    path("me/enrollments/<str:activity_id>", EnrollmentDetailView.as_view(), name="api-enrollment-detail"),
]
