from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from .models import AccountProfile, Lesson


PASSWORD = "Redirect!Study-8642"


class ClassroomRedirectTests(TestCase):
    def setUp(self):
        self.teacher = get_user_model().objects.create_user("redirect_teacher", password=PASSWORD)
        self.student = get_user_model().objects.create_user("redirect_student", password=PASSWORD)
        AccountProfile.objects.create(user=self.teacher, role="teacher")
        AccountProfile.objects.create(user=self.student, role="student")
        self.lesson = Lesson.objects.create(teacher=self.teacher, title="跳转测试课堂")
        self.class_url = reverse("student", args=[self.lesson.code])

    def login_as(self, user, target=""):
        return self.client.post(reverse("login"), {"username": user.username, "password": PASSWORD, "next": target})

    def test_login_does_not_return_to_login_or_registration_page(self):
        for name in ["login", "register_choice", "register_student"]:
            with self.subTest(name=name):
                self.client.logout()
                self.assertRedirects(self.login_as(self.student, reverse(name)), reverse("student_home"))

    def test_student_login_with_teacher_next_returns_to_student_portal(self):
        self.assertRedirects(self.login_as(self.student, reverse("teacher_home")), reverse("student_home"))

    def test_teacher_login_from_own_student_link_opens_teacher_dashboard(self):
        self.assertRedirects(self.login_as(self.teacher, self.class_url), reverse("dashboard", args=[self.lesson.code]))

    def test_authenticated_login_page_goes_to_classroom(self):
        self.client.force_login(self.student)
        self.assertRedirects(self.client.get(reverse("login"), {"next": self.class_url}), self.class_url)

    def test_classroom_survives_switching_to_generic_registration_link(self):
        self.client.get(self.class_url)
        self.client.get(reverse("login"), {"next": self.class_url})
        self.client.get(reverse("register_choice"))
        self.client.get(reverse("register_student"))
        result = self.client.post(reverse("register_student"), {
            "username": "redirect_new_student", "password1": PASSWORD, "password2": PASSWORD, "next": "",
        })
        self.assertRedirects(result, self.class_url)

    def test_registration_with_wrong_role_next_goes_to_role_home(self):
        result = self.client.post(reverse("register_student"), {
            "username": "redirect_new_student", "password1": PASSWORD, "password2": PASSWORD,
            "next": reverse("teacher_home"),
        })
        self.assertRedirects(result, reverse("student_home"))

    def test_blank_post_next_keeps_classroom_saved_on_login_get(self):
        self.client.get(reverse("login"), {"next": self.class_url})
        self.assertRedirects(self.login_as(self.student), self.class_url)

    def test_unsafe_or_nonpage_targets_cannot_be_login_destinations(self):
        for target in ["https://evil.example/", "//evil.example/", "/unknown/", reverse("logout"),
                       reverse("lesson_stats", args=[self.lesson.code]), reverse("export_csv", args=[self.lesson.code])]:
            with self.subTest(target=target):
                self.client.logout()
                self.assertRedirects(self.login_as(self.student, target), reverse("student_home"))

    def test_teacher_cannot_land_on_another_teachers_classroom(self):
        other = get_user_model().objects.create_user("other_teacher")
        lesson = Lesson.objects.create(teacher=other, title="别人的课堂")
        for name in ["student", "dashboard"]:
            with self.subTest(name=name):
                self.client.logout()
                self.assertRedirects(self.login_as(self.teacher, reverse(name, args=[lesson.code])), reverse("teacher_home"))

    def test_deleted_pending_class_falls_back_to_portal(self):
        self.client.get(reverse("login"), {"next": self.class_url})
        self.lesson.delete()
        self.assertRedirects(self.login_as(self.student), reverse("student_home"))

    def test_success_consumes_pending_classroom(self):
        self.client.get(reverse("login"), {"next": self.class_url})
        self.assertRedirects(self.login_as(self.student), self.class_url)
        self.assertNotIn("pending_classroom_url", self.client.session)
        self.assertRedirects(self.client.get(reverse("login")), reverse("student_home"))
