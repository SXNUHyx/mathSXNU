import csv
import io
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from .models import Lesson, Response, ResponseEvent


class ClassroomTests(TestCase):
    def setUp(self):
        self.teacher = get_user_model().objects.create_user("teacher", password="test-password-4278")
        self.other = get_user_model().objects.create_user("other", password="test-password-4278")
        self.lesson = Lesson.objects.create(teacher=self.teacher, title="连续与可导", expected_count=20)
        self.student_url = reverse("student", args=[self.lesson.code])
        self.teacher_client = Client()
        self.teacher_client.force_login(self.teacher)

    def vote(self, client, status="green", note=""):
        client.get(self.student_url)  # Establish the browser session before submission.
        return client.post(self.student_url, {"status": status, "note": note})

    def stats(self):
        return self.teacher_client.get(reverse("lesson_stats", args=[self.lesson.code])).json()

    def test_student_submit_update_and_idempotency(self):
        client = Client()
        self.assertEqual(self.vote(client).status_code, 302)
        self.assertEqual(self.vote(client).status_code, 302)
        self.assertEqual(Response.objects.count(), 1)
        self.assertEqual(ResponseEvent.objects.count(), 1)
        self.vote(client, "red", "这里还没有听懂")
        self.assertEqual(Response.objects.count(), 1)
        self.assertEqual(Response.objects.get().status, "red")
        self.assertEqual(ResponseEvent.objects.count(), 2)
        self.assertEqual(self.stats()["total"], 1)
        self.assertEqual(self.stats()["rows"][2]["count"], 1)

    def test_separate_browsers_and_percentages(self):
        for status in ["green", "yellow", "red", "red"]:
            self.vote(Client(), status)
        stats = self.stats()
        self.assertEqual(stats["total"], 4)
        self.assertEqual([r["percent"] for r in stats["rows"]], [25, 25, 50])
        self.assertEqual(stats["participation"], 20)

    def test_empty_classroom(self):
        stats = self.stats()
        self.assertEqual(stats["total"], 0)
        self.assertTrue(all(r["percent"] == 0 for r in stats["rows"]))

    def test_closed_classroom_rejects_changes_and_can_reopen(self):
        client = Client()
        self.vote(client, "yellow")
        url = reverse("toggle_lesson", args=[self.lesson.code])
        self.teacher_client.post(url, {"action": "close"})
        self.assertEqual(self.vote(client, "red").status_code, 400)
        self.assertEqual(self.vote(Client()).status_code, 400)
        self.assertEqual(Response.objects.get().status, "yellow")
        self.teacher_client.post(url, {"action": "open"})
        self.assertEqual(self.vote(client, "red").status_code, 302)
        self.assertEqual(Response.objects.get().status, "red")

    def test_teacher_pages_require_login(self):
        for name in ["dashboard", "lesson_stats", "lesson_qr", "export_csv"]:
            with self.subTest(name=name):
                result = self.client.get(reverse(name, args=[self.lesson.code]))
                self.assertEqual(result.status_code, 302)
                self.assertIn("/accounts/login/", result.url)

    def test_cross_teacher_access_is_denied(self):
        self.client.force_login(self.other)
        for name in ["dashboard", "lesson_stats", "lesson_qr", "export_csv"]:
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(name, args=[self.lesson.code])).status_code, 404)
        self.assertEqual(self.client.post(reverse("toggle_lesson", args=[self.lesson.code]), {"action": "close"}).status_code, 404)

    def test_invalid_feedback_never_writes(self):
        self.assertEqual(self.vote(self.client, "blue").status_code, 400)
        self.assertEqual(self.vote(self.client, "red", "长" * 301).status_code, 400)
        self.assertEqual(self.vote(self.client, "").status_code, 400)
        self.assertFalse(Response.objects.exists())
        self.assertFalse(ResponseEvent.objects.exists())

    def test_student_does_not_receive_other_feedback(self):
        self.vote(Client(), "red", "只有教师才能看见这段话")
        result = self.client.get(self.student_url)
        self.assertNotContains(result, "只有教师才能看见这段话")
        self.assertNotContains(result, 'id="initial-stats"')

    def test_student_text_is_escaped(self):
        self.vote(self.client, "red", "<script>alert(1)</script>")
        result = self.teacher_client.get(reverse("dashboard", args=[self.lesson.code]))
        self.assertContains(result, "&lt;script&gt;alert(1)&lt;/script&gt;")
        self.assertNotContains(result, "<script>alert(1)</script>")

    def test_latest_and_history_exports_are_distinct_and_safe(self):
        self.vote(self.client, "green", "=1+1")
        self.vote(self.client, "red", " \t@SUM(1)")
        url = reverse("export_csv", args=[self.lesson.code])
        latest = self.teacher_client.get(url)
        rows = list(csv.reader(io.StringIO(latest.content.decode("utf-8-sig"))))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1][5], "需要帮助")
        self.assertTrue(rows[1][6].startswith("'"))
        self.assertEqual(rows[1][4], "1")
        history = self.teacher_client.get(url + "?history=1")
        self.assertEqual(len(list(csv.reader(io.StringIO(history.content.decode("utf-8-sig"))))), 3)
        self.assertNotIn(str(Response.objects.get().participant), latest.content.decode())
        self.assertIn("no-store", latest["Cache-Control"])

    def test_feedback_and_teacher_changes_require_csrf(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.get(self.student_url)
        self.assertEqual(csrf_client.post(self.student_url, {"status": "green"}).status_code, 403)
        token = csrf_client.cookies["csrftoken"].value
        self.assertEqual(csrf_client.post(self.student_url, {"status": "green", "csrfmiddlewaretoken": token}).status_code, 302)
        csrf_client.force_login(self.teacher)
        self.assertEqual(csrf_client.post(reverse("toggle_lesson", args=[self.lesson.code]), {"action": "close"}).status_code, 403)

    def test_creation_and_listing(self):
        response = self.teacher_client.post(reverse("lesson_create"), {"course": "微积分", "title": "定积分", "expected_count": 80})
        self.assertEqual(response.status_code, 302)
        created = Lesson.objects.get(title="定积分")
        self.assertEqual(created.teacher, self.teacher)
        self.assertEqual(len(created.code), 6)
        self.assertContains(self.teacher_client.get(reverse("teacher_home")), "定积分")
        self.assertEqual(self.teacher_client.post(reverse("lesson_create"), {"course": "微积分", "title": "错误人数", "expected_count": -1}).status_code, 200)
        self.assertFalse(Lesson.objects.filter(title="错误人数").exists())

    def test_join_normalizes_code_and_unknown_code_is_clear(self):
        result = self.client.post(reverse("join"), {"code": " " + self.lesson.code.lower() + " "})
        self.assertRedirects(result, self.student_url)
        self.assertEqual(self.client.post(reverse("join"), {"code": "AAAAAA"}).status_code, 400)
        self.assertEqual(self.client.get("/s/ZZZZZZ/").status_code, 404)

    def test_qr_is_generated_locally(self):
        result = self.teacher_client.get(reverse("lesson_qr", args=[self.lesson.code]))
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result["Content-Type"], "image/svg+xml")
        self.assertIn(b"<svg", result.content)

    def test_toggle_requires_valid_action_and_post(self):
        url = reverse("toggle_lesson", args=[self.lesson.code])
        self.assertEqual(self.teacher_client.get(url).status_code, 405)
        self.assertEqual(self.teacher_client.post(url, {"action": "nonsense"}).status_code, 400)
        self.lesson.refresh_from_db()
        self.assertTrue(self.lesson.is_open)

    def test_failed_login_cooldown_and_account_isolation(self):
        url = reverse("login")
        for _ in range(5):
            self.assertEqual(self.client.post(url, {"username": "teacher", "password": "wrong"}).status_code, 200)
        self.assertEqual(self.client.post(url, {"username": "teacher", "password": "test-password-4278"}).status_code, 429)
        self.assertEqual(self.client.post(url, {"username": "other", "password": "test-password-4278"}).status_code, 302)

    def test_failed_login_cooldown_expires(self):
        from datetime import timedelta
        from django.utils import timezone
        from .models import LoginThrottle
        import hashlib
        LoginThrottle.objects.create(key=hashlib.sha256(b"teacher").hexdigest(), failures=5, window_started=timezone.now() - timedelta(minutes=11))
        self.assertEqual(self.client.post(reverse("login"), {"username": "teacher", "password": "test-password-4278"}).status_code, 302)
        self.assertFalse(LoginThrottle.objects.exists())

    def test_health_is_available_over_http_for_container_probe(self):
        from django.test import override_settings
        with override_settings(SECURE_SSL_REDIRECT=True):
            self.assertEqual(self.client.get(reverse("health")).content, b"ok")
            self.assertEqual(self.client.get(reverse("home")).status_code, 301)
