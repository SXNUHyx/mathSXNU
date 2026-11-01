import importlib.util
from pathlib import Path
import tempfile
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from .models import AccountProfile


@override_settings(SESSION_COOKIE_SECURE=True, CSRF_COOKIE_SECURE=True, SECURE_SSL_REDIRECT=False,
                   PUBLIC_ORIGIN="https://classroom.school.cn")
class SecureTransportTests(TestCase):
    def test_http_login_explains_transport_problem_without_attempting_auth(self):
        user = get_user_model().objects.create_user("transport_teacher", password="Login!1432-example")
        AccountProfile.objects.create(user=user, role="teacher")
        result = self.client.post(reverse("login"), {"username": user.username, "password": "Login!1432-example"})
        self.assertContains(result, "当前访问方式无法保持登录", status_code=400)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertContains(result, "https://classroom.school.cn/accounts/login/", status_code=400)

    def test_http_signup_does_not_create_unusable_login(self):
        result = self.client.post(reverse("register_student"), {"username": "http_student", "password1": "Long!password1432", "password2": "Long!password1432"})
        self.assertEqual(result.status_code, 400)
        self.assertFalse(get_user_model().objects.exists())

    def test_https_still_supports_normal_login(self):
        user = get_user_model().objects.create_user("transport_teacher", password="Login!1432-example")
        AccountProfile.objects.create(user=user, role="teacher")
        result = self.client.post(reverse("login"), {"username": user.username, "password": "Login!1432-example"}, secure=True)
        self.assertRedirects(result, reverse("teacher_home"))
        self.assertTrue(result.cookies["sessionid"]["secure"])

    def test_http_does_not_block_health_probe(self):
        self.assertEqual(self.client.get(reverse("health")).content, b"ok")


class AccessConfigurationTests(SimpleTestCase):
    def module(self):
        spec = importlib.util.spec_from_file_location("set_access_mode", Path(__file__).resolve().parent.parent / "scripts/set-access-mode.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_mode_switch_preserves_secret_unknown_settings_and_private_backup(self):
        module = self.module()
        original = "# private settings\nDJANGO_SECRET_KEY=fixture-not-a-real-key\nOTHER_SETTING=keep-me\nCLASSROOM_DOMAIN=old.school.cn\n"
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / ".env"
            target.write_text(original)
            backup = module.configure(target, "192.0.2.25", True)
            self.assertEqual(backup.read_text(), original)
            content = target.read_text()
            self.assertIn("DJANGO_SECRET_KEY=fixture-not-a-real-key\n", content)
            self.assertIn("OTHER_SETTING=keep-me\n", content)
            self.assertIn("CLASSROOM_SCHEME=http\n", content)
            self.assertIn("CLASSROOM_ALLOW_INSECURE_HTTP=1\n", content)
            module.configure(target, "classroom.school.cn", False)
            content = target.read_text()
            self.assertIn("CLASSROOM_SCHEME=https\n", content)
            self.assertIn("CLASSROOM_ALLOW_INSECURE_HTTP=0\n", content)
            self.assertEqual(content.count("CLASSROOM_DOMAIN="), 1)

    def test_invalid_host_cannot_write_config_or_reset_secret(self):
        module = self.module()
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / ".env"
            target.write_text("DJANGO_SECRET_KEY=fixture-not-a-real-key\n")
            before = target.read_bytes()
            for host, http in [("https://school.cn", True), ("a.cn\nEVIL=1", True), ("192.0.2.25", False)]:
                with self.subTest(host=host), self.assertRaises(ValueError):
                    module.configure(target, host, http)
            self.assertEqual(target.read_bytes(), before)
