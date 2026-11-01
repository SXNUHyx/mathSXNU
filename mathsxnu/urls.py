from django.contrib.auth import views as auth_views
from django.urls import path
from feedback import views
from feedback.auth import TeacherLoginView, register, registration_choice

urlpatterns = [
    path("health/", views.health, name="health"),
    path("", views.home, name="home"),
    path("join/", views.join, name="join"),
    path("accounts/login/", TeacherLoginView.as_view(), name="login"),
    path("accounts/register/", registration_choice, name="register_choice"),
    path("accounts/register/teacher/", register, {"role": "teacher"}, name="register_teacher"),
    path("accounts/register/student/", register, {"role": "student"}, name="register_student"),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("teacher/", views.teacher_home, name="teacher_home"),
    path("student/", views.student_home, name="student_home"),
    path("teacher/new/", views.lesson_create, name="lesson_create"),
    path("teacher/<str:code>/", views.dashboard, name="dashboard"),
    path("teacher/<str:code>/stats/", views.lesson_stats, name="lesson_stats"),
    path("teacher/<str:code>/qr/", views.lesson_qr, name="lesson_qr"),
    path("teacher/<str:code>/toggle/", views.toggle_lesson, name="toggle_lesson"),
    path("teacher/<str:code>/export/", views.export_csv, name="export_csv"),
    path("s/<str:code>/", views.student, name="student"),
]
