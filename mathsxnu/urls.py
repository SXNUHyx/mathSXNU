from django.contrib.auth import views as auth_views
from django.urls import path
from feedback import views
from feedback import course_views
from feedback import reports
from feedback import ai_views
from feedback import management_views
from django.contrib.auth.decorators import login_required
from django.urls import reverse_lazy
from feedback.auth import TeacherLoginView, register, registration_choice

urlpatterns = [
    path('developer/lessons/',management_views.lessons,name='developer_lessons'),
    path('developer/',management_views.dashboard,name='developer_home'),
    path('developer/users/new/',management_views.new_user,name='developer_user_new'),
    path('developer/users/export/',management_views.export_users,name='developer_export'),
    path('developer/users/<int:pk>/',management_views.user_detail,name='developer_user'),
    path('developer/users/<int:pk>/<str:action>/',management_views.user_action,name='developer_user_action'),
    path('developer/audit/',management_views.audit_logs,name='developer_audit'),
    path('developer/api/users/',management_views.api_users,name='developer_api_users'),
    path('developer/api/users/<int:pk>/',management_views.api_user_detail,name='developer_api_user'),
    path('developer/api/users/<int:pk>/actions/',management_views.api_user_action,name='developer_api_action'),
    path('developer/api/audit/',management_views.api_audit,name='developer_api_audit'),
    path('accounts/password/change/',login_required(auth_views.PasswordChangeView.as_view(template_name='account_password_change.html',success_url=reverse_lazy('password_change_done'))),name='password_change'),
    path('accounts/password/done/',login_required(auth_views.PasswordChangeDoneView.as_view(template_name='account_password_done.html')),name='password_change_done'),
    path("health/", views.health, name="health"),
    path("", views.home, name="home"),
    path("mathai/", ai_views.mathai, name="mathai"),
    path("mathai/<int:pk>/", ai_views.mathai, name="ai_chat"),
    path("mathai/<int:pk>/delete/", ai_views.delete_conversation, name="ai_delete"),
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
    path("teacher/<str:code>/answers/", reports.answer_report, name="answer_report"),
    path("teacher/<str:code>/answers.docx", reports.export_answers, name="export_answers"),
    path("teacher/<str:code>/delete/", course_views.lesson_delete, name="lesson_delete"),
    path("teacher/<str:code>/restore/", course_views.lesson_restore, name="lesson_restore"),
    path("teacher/<str:code>/blocks/new/", course_views.block_edit, name="block_create"),
    path("teacher/<str:code>/blocks/<int:pk>/edit/", course_views.block_edit, name="block_edit"),
    path("teacher/<str:code>/blocks/<int:pk>/delete/", course_views.block_delete, name="block_delete"),
    path("teacher/<str:code>/materials/new/", course_views.material_upload, name="material_upload"),
    path("teacher/<str:code>/materials/<int:pk>/delete/", course_views.material_delete, name="material_delete"),
    path("teacher/<str:code>/feedback/<int:pk>/reply/", course_views.reply_create, name="reply_create"),
    path("materials/<int:pk>/", course_views.material_file, name="material_file"),
    path("questions/files/<int:pk>/", course_views.question_file, name="question_file"),
    path("s/<str:code>/updates/", course_views.student_updates, name="student_updates"),
    path("s/<str:code>/read/", course_views.replies_read, name="replies_read"),
    path("s/<str:code>/", views.student, name="student"),
]
