from django.contrib.auth import views as auth_views
from django.http import JsonResponse
from django.urls import path

from portal import views

urlpatterns = [
    path("health/", lambda request: JsonResponse({"status": "ok"}), name="health"),
    path("", views.home, name="home"),
    path("accounts/register/", views.register, name="register"),
    path(
        "accounts/login/",
        auth_views.LoginView.as_view(template_name="registration/login.html", redirect_authenticated_user=True),
        name="login",
    ),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("profile/", views.profile, name="profile"),
    path("rounds/<slug:slug>/", views.round_detail, name="round_detail"),
    path("rounds/<slug:slug>/start/", views.start_round, name="start_round"),
    path("rounds/<slug:slug>/play/", views.play_round, name="play_round"),
    path("submissions/<int:pk>/", views.submission_result, name="submission_result"),
    path("leaderboard/", views.leaderboard, name="leaderboard"),
    path("staff/", views.staff_dashboard, name="staff_dashboard"),
    path("staff/participants/", views.staff_participants, name="staff_participants"),
    path("staff/results/publish/", views.publish_results, name="publish_results"),
    path("staff/submissions/<int:pk>/review/", views.review_submission, name="review_submission"),
]
