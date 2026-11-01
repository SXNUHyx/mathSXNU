from django.contrib.auth import views as auth_views
from django.urls import path
from feedback import views
from feedback import course_views
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
    path("student/notifications/", course_views.student_notifications, name="student_notifications"),
    path("teacher/trash/", course_views.lesson_trash, name="lesson_trash"),
    path("teacher/new/", views.lesson_create, name="lesson_create"),
    path("teacher/<str:code>/", views.dashboard, name="dashboard"),
    path("teacher/<str:code>/stats/", views.lesson_stats, name="lesson_stats"),
    path("teacher/<str:code>/qr/", views.lesson_qr, name="lesson_qr"),
    path("teacher/<str:code>/toggle/", views.toggle_lesson, name="toggle_lesson"),
    path("teacher/<str:code>/export/", views.export_csv, name="export_csv"),
    path("teacher/<str:code>/delete/", course_views.lesson_delete, name="lesson_delete"),
    path("teacher/<str:code>/restore/", course_views.lesson_restore, name="lesson_restore"),
    path("teacher/<str:code>/blocks/new/", course_views.block_edit, name="block_create"),
    path("teacher/<str:code>/blocks/<int:pk>/edit/", course_views.block_edit, name="block_edit"),
    path("teacher/<str:code>/blocks/<int:pk>/delete/", course_views.block_delete, name="block_delete"),
    path("teacher/<str:code>/materials/new/", course_views.material_upload, name="material_upload"),
    path("teacher/<str:code>/materials/<int:pk>/delete/", course_views.material_delete, name="material_delete"),
    path("teacher/<str:code>/feedback/<int:pk>/reply/", course_views.reply_create, name="reply_create"),
    path("materials/<int:pk>/", course_views.material_file, name="material_file"),
    path("s/<str:code>/updates/", course_views.student_updates, name="student_updates"),
    path("s/<str:code>/read/", course_views.replies_read, name="replies_read"),
    path("s/<str:code>/", views.student, name="student"),
]
