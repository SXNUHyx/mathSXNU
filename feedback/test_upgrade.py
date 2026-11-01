"""Exercise the actual pre-registration -> registration database upgrade."""
import uuid
from django.contrib.auth.hashers import make_password
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.urls import reverse


class RegistrationUpgradeTests(TransactionTestCase):
    def test_existing_teachers_passwords_classrooms_and_anonymous_records_survive(self):
        old = [("feedback", "0002_loginthrottle")]
        new = MigrationExecutor(connection).loader.graph.leaf_nodes("feedback")
        self.addCleanup(lambda: MigrationExecutor(connection).migrate(new))
        executor = MigrationExecutor(connection)
        executor.migrate(old)
        apps = executor.loader.project_state(old).apps
        User = apps.get_model("auth", "User")
        Lesson = apps.get_model("feedback", "Lesson")
        Response = apps.get_model("feedback", "Response")
        Event = apps.get_model("feedback", "ResponseEvent")
        password_hash = make_password("OldTeacher!1428")
        user = User.objects.create(username="legacy_teacher", password=password_hash)
        lesson = Lesson.objects.create(teacher_id=user.pk, title="原来的课堂", code="ABC234")
        participant = uuid.uuid4()
        Response.objects.create(lesson_id=lesson.pk, participant=participant, status="red", note="升级前的留言")
        Event.objects.create(lesson_id=lesson.pk, participant=participant, status="red", note="升级前的留言")
        executor = MigrationExecutor(connection)
        executor.migrate(new)
        from .models import AccountProfile, Lesson as CurrentLesson, Response as CurrentResponse, ResponseEvent
        from django.contrib.auth import get_user_model
        current_user = get_user_model().objects.get(pk=user.pk)
        self.assertEqual(AccountProfile.objects.get(user_id=user.pk).role, "teacher")
        self.assertEqual(current_user.password, password_hash)
        self.assertTrue(current_user.check_password("OldTeacher!1428"))
        self.assertEqual(CurrentLesson.objects.get(pk=lesson.pk).title, "原来的课堂")
        self.assertEqual(CurrentResponse.objects.get().participant, participant)
        self.assertIsNone(CurrentResponse.objects.get().user_id)
        self.assertEqual(ResponseEvent.objects.get().note, "升级前的留言")
        result = self.client.post(reverse("login"), {"username": "legacy_teacher", "password": "OldTeacher!1428"})
        self.assertRedirects(result, reverse("teacher_home"))
        self.assertContains(self.client.get(reverse("dashboard", args=[lesson.code])), "原来的课堂")
