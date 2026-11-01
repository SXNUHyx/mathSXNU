import csv
import io
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from .models import AccountProfile, ClassroomMembership, Lesson, Response, ResponseEvent

PASSWORD = "Study!Math-7842-Example"


class RegistrationTests(TestCase):
    def register(self, registration_role="student", username="student_one", **extra):
        return self.client.post(reverse("register_" + registration_role), {
            "username": username, "password1": PASSWORD, "password2": PASSWORD, **extra,
        })

    def test_student_registration_hashes_password_and_logs_in(self):
        result = self.register(is_staff="1", is_superuser="1", role="teacher")
        self.assertRedirects(result, reverse("student_home"))
        user = get_user_model().objects.get()
        self.assertTrue(user.check_password(PASSWORD))
        self.assertNotEqual(user.password, PASSWORD)
        self.assertFalse(user.is_staff or user.is_superuser)
        self.assertEqual(user.account_profile.role, "student")
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)

    def test_teacher_registration_can_create_only_own_classroom(self):
        result = self.register("teacher", "teacher_one", role="student", is_superuser="1")
        self.assertRedirects(result, reverse("teacher_home"))
        user = get_user_model().objects.get()
        self.assertEqual(user.account_profile.role, "teacher")
        self.assertFalse(user.is_superuser or user.is_staff)
        result = self.client.post(reverse("lesson_create"), {"course": "微积分", "title": "极限"})
        self.assertEqual(result.status_code, 302)
        self.assertEqual(Lesson.objects.get().teacher_id, user.pk)

    def test_duplicate_username_case_insensitive_and_normalized(self):
        get_user_model().objects.create_user("ExistingUser")
        result = self.register(username="EXISTINGUSER")
        self.assertContains(result, "这个用户名已被使用")
        self.assertEqual(get_user_model().objects.count(), 1)
        self.register(username="New_Student")
        self.assertTrue(get_user_model().objects.filter(username="new_student").exists())
        self.client.logout()
        self.assertRedirects(self.client.post(reverse("login"), {"username": "New_Student", "password": PASSWORD}), reverse("student_home"))

    def test_invalid_username_password_and_confirmation_do_not_create_users(self):
        for data in [
            {"username": "<script>"},
            {"password1": "12345678", "password2": "12345678"},
            {"password2": "does-not-match"},
        ]:
            with self.subTest(data=data):
                self.assertEqual(self.register(**data).status_code, 200)
                self.assertFalse(get_user_model().objects.exists())
                self.assertFalse(AccountProfile.objects.exists())

    def test_registration_requires_csrf(self):
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(client.post(reverse("register_student"), {"username": "csrf_check", "password1": PASSWORD, "password2": PASSWORD}).status_code, 403)

    def test_registration_redirect_is_local_and_preserves_class_link(self):
        teacher = get_user_model().objects.create_user("owner")
        lesson = Lesson.objects.create(teacher=teacher, title="极限")
        self.assertRedirects(self.register(next=reverse("student", args=[lesson.code])), reverse("student", args=[lesson.code]))
        self.client.logout()
        self.assertRedirects(self.register(username="another_student", next="https://evil.example/"), reverse("student_home"))

    def test_login_redirect_follows_role_and_superuser_works_without_profile(self):
        for role in ["teacher", "student"]:
            with self.subTest(role=role):
                user = get_user_model().objects.create_user(role, password=PASSWORD)
                AccountProfile.objects.create(user=user, role=role)
                self.assertRedirects(self.client.post(reverse("login"), {"username": role, "password": PASSWORD}), reverse(role + "_home"))
                self.client.logout()
        get_user_model().objects.create_superuser("admin", password=PASSWORD)
        self.assertRedirects(self.client.post(reverse("login"), {"username": "admin", "password": PASSWORD}), reverse("teacher_home"))

    def test_authenticated_users_cannot_change_role_by_registering(self):
        self.register()
        result = self.register("teacher", "second_teacher")
        self.assertRedirects(result, reverse("student_home"))
        self.assertEqual(get_user_model().objects.count(), 1)
        self.assertEqual(AccountProfile.objects.get().role, "student")


class StudentAuthorizationTests(TestCase):
    def setUp(self):
        self.teacher = get_user_model().objects.create_user("owner")
        AccountProfile.objects.create(user=self.teacher, role="teacher")
        self.student = get_user_model().objects.create_user("student")
        AccountProfile.objects.create(user=self.student, role="student")
        self.lesson = Lesson.objects.create(teacher=self.teacher, title="连续与可导")
        self.url = reverse("student", args=[self.lesson.code])

    def test_all_teacher_endpoints_deny_student(self):
        self.client.force_login(self.student)
        for name, args in [("teacher_home", []), ("lesson_create", []), ("dashboard", [self.lesson.code]),
                           ("lesson_stats", [self.lesson.code]), ("lesson_qr", [self.lesson.code]), ("export_csv", [self.lesson.code])]:
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(name, args=args)).status_code, 403)
        self.assertEqual(self.client.post(reverse("lesson_create"), {"course": "illegal", "title": "illegal"}).status_code, 403)
        self.assertEqual(self.client.post(reverse("toggle_lesson", args=[self.lesson.code]), {"action": "close"}).status_code, 403)
        self.assertEqual(Lesson.objects.count(), 1)

    def test_anonymous_feedback_requires_login(self):
        for result in [self.client.get(self.url), self.client.post(self.url, {"status": "red"})]:
            self.assertEqual(result.status_code, 302)
            self.assertIn("/accounts/login/", result.url)
        self.assertFalse(Response.objects.exists())

    def test_same_account_on_two_browsers_only_counts_once(self):
        first, second = Client(), Client()
        for client in [first, second]:
            client.force_login(self.student)
        first.post(self.url, {"status": "red", "note": "第一设备", "real_name": "张同学", "student_number": "00123"})
        second.post(self.url, {"status": "green", "note": "第二设备", "real_name": "张同学", "student_number": "00123"})
        self.assertEqual(Response.objects.count(), 1)
        self.assertEqual(Response.objects.get().user_id, self.student.pk)
        self.assertEqual(Response.objects.get().status, "green")
        self.assertEqual(ResponseEvent.objects.count(), 2)
        self.assertEqual(ClassroomMembership.objects.count(), 1)
        self.assertContains(first.get(self.url), "第二设备")

    def test_teacher_can_preview_but_cannot_submit(self):
        self.client.force_login(self.teacher)
        self.assertContains(self.client.get(self.url), "教师账号不能提交学生反馈")
        self.assertEqual(self.client.post(self.url, {"status": "green"}).status_code, 403)
        self.assertFalse(Response.objects.exists())

    def test_my_learning_does_not_show_other_students_memberships_or_notes(self):
        other = get_user_model().objects.create_user("other_student")
        other_class = Lesson.objects.create(teacher=self.teacher, title="其他学生的私有列表")
        ClassroomMembership.objects.create(lesson=other_class, student=other)
        self.client.force_login(other)
        self.client.post(self.url, {"status": "red", "note": "其他学生的个人说明", "real_name": "其他学生", "student_number": "002"})
        self.client.force_login(self.student)
        self.client.get(self.url)
        page = self.client.get(reverse("student_home"))
        self.assertContains(page, "连续与可导")
        self.assertNotContains(page, "其他学生的私有列表")
        self.assertNotContains(self.client.get(self.url), "其他学生的个人说明")

    def test_legacy_and_account_feedback_remain_separate_and_exports_hide_username(self):
        import uuid
        Response.objects.create(lesson=self.lesson, participant=uuid.uuid4(), status="yellow", note="历史记录")
        self.client.force_login(self.student)
        self.client.post(self.url, {"status": "red", "real_name": "张同学", "student_number": "00123"})
        self.client.force_login(self.teacher)
        stats = self.client.get(reverse("lesson_stats", args=[self.lesson.code])).json()
        self.assertEqual((stats["total"], stats["account_count"], stats["legacy_count"]), (2, 1, 1))
        data = self.client.get(reverse("export_csv", args=[self.lesson.code])).content.decode("utf-8-sig")
        self.assertNotIn(self.student.username, data)
        rows = list(csv.reader(io.StringIO(data)))
        self.assertEqual(len(rows), 3)
        self.assertEqual({r[8] for r in rows[1:]}, {"历史不记名反馈", "学生账号反馈"})
