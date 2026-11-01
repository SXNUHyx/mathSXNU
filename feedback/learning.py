from django.urls import reverse
from django.utils import timezone
from .models import KnowledgeBlock


def content_context(lesson):
    materials = list(lesson.materials.filter(deleted_at__isnull=True))
    blocks = list(lesson.blocks.all())
    sections = []
    for kind, label in KnowledgeBlock.Kind.choices:
        sections.append({"kind": kind, "label": label,
                         "blocks": [{"item": block, "materials": [m for m in materials if m.block_id == block.pk]}
                                    for block in blocks if block.kind == kind],
                         "materials": [m for m in materials if m.block_id is None and m.section == kind]})
    return {"content_sections": sections}


def reply_payload(reply):
    return {"id": reply.pk, "question": reply.question_text, "message": reply.message,
            "time": timezone.localtime(reply.created_at).strftime("%m-%d %H:%M"),
            "unread": reply.student_read_at is None}


def feedback_payload(response):
    return {"id": response.pk, "event_id": getattr(response, "latest_event_id", None),
            "can_reply": response.user_id is not None,
            "status": response.status, "label": response.get_status_display(), "text": response.note,
            "student_name": response.real_name or (f"账号：{response.user.username}" if response.user_id else "历史不记名"),
            "student_number": response.student_number or "未填写",
            "time": timezone.localtime(response.updated_at).strftime("%H:%M:%S"),
            "reply_url": reverse("reply_create", args=[response.lesson.code, response.pk]),
            "replies": [reply_payload(r) for r in response.replies.all()][-5:]}
