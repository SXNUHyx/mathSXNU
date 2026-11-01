import secrets
from django.conf import settings
from django.db import models
from django.utils import timezone


def classroom_code():
    return "".join(secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(6))


class Lesson(models.Model):
    teacher = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    code = models.CharField(max_length=6, unique=True, default=classroom_code)
    title = models.CharField(max_length=100)
    course = models.CharField(max_length=100, default="高等数学")
    expected_count = models.PositiveIntegerField(null=True, blank=True)
    is_open = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class Response(models.Model):
    class Status(models.TextChoices):
        GREEN = "green", "听懂了"
        YELLOW = "yellow", "有点疑惑"
        RED = "red", "需要帮助"

    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name="responses")
    participant = models.UUIDField()
    status = models.CharField(max_length=6, choices=Status.choices)
    note = models.CharField(max_length=300, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["lesson", "participant"], name="one_device_per_lesson")]


class ResponseEvent(models.Model):
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name="events")
    participant = models.UUIDField()
    status = models.CharField(max_length=6, choices=Response.Status.choices)
    note = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class LoginThrottle(models.Model):
    """Short-lived failure counters; no passwords or raw usernames stored."""
    key = models.CharField(max_length=64, primary_key=True)
    failures = models.PositiveIntegerField(default=0)
    window_started = models.DateTimeField(default=timezone.now)
