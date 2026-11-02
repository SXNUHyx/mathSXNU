import secrets
import uuid
from django.conf import settings
from django.db import models
from django.utils import timezone
from pathlib import Path


def classroom_code():
    return "".join(secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(6))


class Lesson(models.Model):
    teacher = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    code = models.CharField(max_length=6, unique=True, default=classroom_code)
    title = models.CharField(max_length=100)
    course = models.CharField(max_length=100, default="课程")
    expected_count = models.PositiveIntegerField(null=True, blank=True)
    is_open = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]


class Response(models.Model):
    class Status(models.TextChoices):
        GREEN = "green", "听懂了"
        YELLOW = "yellow", "有点疑惑"
        RED = "red", "需要帮助"

    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name="responses")
    participant = models.UUIDField()
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="classroom_responses")
    status = models.CharField(max_length=6, choices=Status.choices)
    note = models.CharField(max_length=3000, blank=True)
    block = models.ForeignKey('KnowledgeBlock', null=True, blank=True, on_delete=models.SET_NULL, related_name='feedbacks')
    real_name = models.CharField(max_length=50, blank=True)
    student_number = models.CharField(max_length=40, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["lesson", "participant"], name="one_device_per_lesson"),
            models.UniqueConstraint(fields=["lesson", "user"], condition=models.Q(user__isnull=False), name="one_account_per_lesson"),
        ]


class ResponseEvent(models.Model):
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name="events")
    participant = models.UUIDField()
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    status = models.CharField(max_length=6, choices=Response.Status.choices)
    note = models.CharField(max_length=3000, blank=True)
    block = models.ForeignKey('KnowledgeBlock', null=True, blank=True, on_delete=models.SET_NULL)
    block_title = models.CharField(max_length=120, blank=True)
    real_name = models.CharField(max_length=50, blank=True)
    student_number = models.CharField(max_length=40, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class LoginThrottle(models.Model):
    """Short-lived failure counters; no passwords or raw usernames stored."""
    key = models.CharField(max_length=64, primary_key=True)
    failures = models.PositiveIntegerField(default=0)
    window_started = models.DateTimeField(default=timezone.now)


class AccountProfile(models.Model):
    class Role(models.TextChoices):
        TEACHER = "teacher", "教师"
        STUDENT = "student", "学生"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="account_profile")
    role = models.CharField(max_length=7, choices=Role.choices, default=Role.STUDENT)
    participant = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    real_name = models.CharField(max_length=50, blank=True)
    student_number = models.CharField(max_length=40, blank=True)


class ClassroomMembership(models.Model):
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE)
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="classroom_memberships")
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-joined_at"]
        constraints = [models.UniqueConstraint(fields=["lesson", "student"], name="one_membership_per_account")]


class KnowledgeBlock(models.Model):
    class Kind(models.TextChoices):
        KNOWLEDGE = "knowledge", "知识点"
        KEY = "key", "重点"
        DIFFICULT = "difficult", "难点"

    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name="blocks")
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.KNOWLEDGE)
    title = models.CharField(max_length=100)
    body = models.TextField(max_length=20000, blank=True)
    position = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["position", "pk"]

    def __str__(self):
        return f"{self.get_kind_display()} · {self.title}"


def material_path(instance, filename):
    return f"lessons/{instance.lesson_id}/{uuid.uuid4().hex}{Path(filename).suffix.lower()}"


class CourseMaterial(models.Model):
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name="materials")
    section = models.CharField(max_length=10, choices=KnowledgeBlock.Kind.choices, default=KnowledgeBlock.Kind.KNOWLEDGE)
    block = models.ForeignKey(KnowledgeBlock, on_delete=models.SET_NULL, null=True, blank=True, related_name="materials")
    title = models.CharField(max_length=100)
    file = models.FileField(upload_to=material_path)
    original_name = models.CharField(max_length=255)
    content_type = models.CharField(max_length=100)
    is_image = models.BooleanField(default=False)
    size = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]


class TeacherReply(models.Model):
    response = models.ForeignKey(Response, on_delete=models.CASCADE, related_name="replies")
    teacher = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    question_event = models.ForeignKey(ResponseEvent, on_delete=models.SET_NULL, null=True, blank=True)
    question_text = models.CharField(max_length=3000, blank=True)
    message = models.TextField(max_length=5000)
    created_at = models.DateTimeField(auto_now_add=True)
    student_read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at", "pk"]


def question_file_path(instance, filename):
    return f"questions/{instance.event_id}/{uuid.uuid4().hex}{Path(filename).suffix.lower()}"


class QuestionAttachment(models.Model):
    event = models.ForeignKey(ResponseEvent, on_delete=models.CASCADE, related_name='attachments')
    file = models.FileField(upload_to=question_file_path)
    original_name = models.CharField(max_length=255)
    content_type = models.CharField(max_length=100)
    is_image = models.BooleanField(default=False)
    size = models.PositiveIntegerField()


class AIConversation(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='ai_conversations')
    lesson = models.ForeignKey(Lesson, null=True, blank=True, on_delete=models.SET_NULL)
    provider = models.CharField(max_length=12, default='local')
    share_course = models.BooleanField(default=False)
    title = models.CharField(max_length=80)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-pk']


class AITurn(models.Model):
    conversation = models.ForeignKey(AIConversation, on_delete=models.CASCADE, related_name='turns')
    request_id = models.UUIDField(unique=True)
    question = models.TextField(max_length=3000)
    answer = models.TextField(blank=True)
    status = models.CharField(max_length=10, default='pending')
    sources = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'pk']
