from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import FileResponse, Http404, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST
from .forms import KnowledgeBlockForm, CourseMaterialForm, ReplyForm
from .learning import content_context, reply_payload
from .models import Lesson, KnowledgeBlock, CourseMaterial, Response, ResponseEvent, TeacherReply, ClassroomMembership
from .roles import teacher_required, account_role


def owned(request, code):
    return get_object_or_404(Lesson, code=code, teacher=request.user, deleted_at__isnull=True)


@teacher_required
def lesson_delete(request, code):
    lesson = owned(request, code)
    if request.method == "POST":
        if request.POST.get("confirm") != "yes":
            return HttpResponseBadRequest("请确认删除课堂。")
        with transaction.atomic():
            Lesson.objects.filter(pk=lesson.pk, teacher=request.user).update(deleted_at=timezone.now(), is_open=False)
        messages.success(request, "课堂已移入回收站，学生无法继续访问。可在回收站恢复。")
        return redirect("teacher_home")
    return render(request, "lesson_delete.html", {"lesson": lesson})


@teacher_required
def lesson_trash(request):
    return render(request, "lesson_trash.html", {"lessons": Lesson.objects.filter(teacher=request.user, deleted_at__isnull=False)})


@teacher_required
@require_POST
def lesson_restore(request, code):
    lesson = get_object_or_404(Lesson, code=code, teacher=request.user, deleted_at__isnull=False)
    lesson.deleted_at = None
    lesson.save(update_fields=["deleted_at"])
    messages.success(request, "课堂已恢复，仍保持结束状态；需要收集反馈时请重新开放。")
    return redirect("dashboard", code=code)


@teacher_required
def block_edit(request, code, pk=None):
    lesson = owned(request, code)
    block = get_object_or_404(KnowledgeBlock, pk=pk, lesson=lesson) if pk else None
    initial = {"kind": request.GET.get("kind", KnowledgeBlock.Kind.KNOWLEDGE)} if not block else {}
    form = KnowledgeBlockForm(request.POST if request.method == "POST" else None, instance=block, initial=initial)
    if request.method == "POST" and form.is_valid():
        block = form.save(commit=False)
        block.lesson = lesson
        with transaction.atomic():
            block.save()
            block.materials.update(section=block.kind)
        messages.success(request, "课程模块已保存。")
        return redirect(reverse("dashboard", args=[code]) + "#section-" + block.kind)
    return render(request, "content_form.html", {"lesson": lesson, "form": form, "kind": "block", "editing": bool(pk)})


@teacher_required
@require_POST
def block_delete(request, code, pk):
    block = get_object_or_404(KnowledgeBlock, pk=pk, lesson=owned(request, code))
    section = block.kind
    with transaction.atomic():
        block.materials.update(section=section)
        block.delete()
    messages.success(request, "模块已删除，原文件仍保留在对应板块的资料区。")
    return redirect(reverse("dashboard", args=[code]) + "#section-" + section)


@teacher_required
def material_upload(request, code):
    lesson = owned(request, code)
    section = request.GET.get("section") or request.POST.get("section") or KnowledgeBlock.Kind.KNOWLEDGE
    if section not in KnowledgeBlock.Kind.values:
        return HttpResponseBadRequest("请选择知识点、重点或难点板块。")
    initial = {}
    if request.GET.get("block"):
        try:
            block_pk = int(request.GET["block"])
        except ValueError:
            return HttpResponseBadRequest("请选择有效的模块。")
        initial["block"] = get_object_or_404(lesson.blocks, pk=block_pk, kind=section).pk
    form = CourseMaterialForm(request.POST if request.method == "POST" else None, request.FILES or None,
                              lesson=lesson, section=section, initial=initial)
    if request.method == "POST" and form.is_valid():
        material = form.save(commit=False)
        material.lesson = lesson
        material.original_name = form.cleaned_data["file"].name
        material.size = form.cleaned_data["file"].size
        material.content_type = form.inspected_type
        material.is_image = form.inspected_image
        material.save()
        messages.success(request, "图片或课程资料已上传，课堂成员现在可以查看。")
        return redirect(reverse("dashboard", args=[code]) + "#section-" + material.section)
    return render(request, "content_form.html", {"lesson": lesson, "form": form, "kind": "upload"})


@teacher_required
@require_POST
def material_delete(request, code, pk):
    material = get_object_or_404(CourseMaterial, pk=pk, lesson=owned(request, code), deleted_at__isnull=True)
    material.deleted_at = timezone.now()
    material.save(update_fields=["deleted_at"])
    messages.success(request, "资料已从课堂中移除，文件仍保留在私有备份范围内。")
    return redirect(reverse("dashboard", args=[code]) + "#course-content")


@login_required
@never_cache
def material_file(request, pk):
    material = get_object_or_404(CourseMaterial.objects.select_related("lesson"), pk=pk, deleted_at__isnull=True, lesson__deleted_at__isnull=True)
    allowed = material.lesson.teacher_id == request.user.pk if account_role(request.user) == "teacher" else ClassroomMembership.objects.filter(lesson=material.lesson, student=request.user).exists()
    if not allowed:
        raise Http404
    try:
        response = FileResponse(material.file.open("rb"), as_attachment=not material.is_image, filename=material.original_name, content_type=material.content_type)
    except FileNotFoundError as exc:
        raise Http404("文件暂不可用，请联系任课教师。") from exc
    response["Content-Security-Policy"] = "default-src 'none'; sandbox"
    response["X-Content-Type-Options"] = "nosniff"
    return response


@teacher_required
def reply_create(request, code, pk):
    lesson = owned(request, code)
    response = get_object_or_404(Response.objects.select_related("user"), pk=pk, lesson=lesson)
    if not response.user_id:
        return HttpResponseBadRequest("历史不记名反馈无法确定接收账号，不能发送定向回复。")
    initial_event = lesson.events.filter(participant=response.participant).order_by("-pk").first()
    form = ReplyForm(request.POST if request.method == "POST" else None, initial={"event_id": initial_event.pk if initial_event else None})
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            locked = get_object_or_404(Response.objects.select_for_update(), pk=pk, lesson=lesson, lesson__deleted_at__isnull=True)
            event = None
            if form.cleaned_data["event_id"]:
                event = get_object_or_404(ResponseEvent, pk=form.cleaned_data["event_id"], lesson=lesson, participant=locked.participant)
            TeacherReply.objects.create(response=locked, teacher=request.user, question_event=event,
                                        question_text=event.note if event else locked.note, message=form.cleaned_data["message"])
        messages.success(request, "回复已发送，学生在线时将自动收到提示。")
        return redirect(reverse("dashboard", args=[code]) + "#feedback")
    return render(request, "reply_form.html", {"lesson": lesson, "response": response, "form": form})


def student_lesson(request, code):
    if account_role(request.user) != "student":
        raise Http404
    return get_object_or_404(Lesson, code=code, deleted_at__isnull=True, classroommembership__student=request.user)


@login_required
@never_cache
def student_updates(request, code):
    lesson = student_lesson(request, code)
    replies = TeacherReply.objects.filter(response__lesson=lesson, response__user=request.user)
    return JsonResponse({"is_open": lesson.is_open, "replies": [reply_payload(r) for r in replies]})


@login_required
@require_POST
def replies_read(request, code):
    lesson = student_lesson(request, code)
    try:
        up_to = int(request.POST.get("up_to", ""))
        if up_to < 1:
            raise ValueError
    except ValueError:
        return HttpResponseBadRequest("请指定已经查看的回复。")
    TeacherReply.objects.filter(response__lesson=lesson, response__user=request.user,
                               pk__lte=up_to, student_read_at__isnull=True).update(student_read_at=timezone.now())
    if "application/json" in request.headers.get("Accept", ""):
        return JsonResponse({"ok": True})
    return redirect(reverse("student", args=[code]) + "#teacher-replies")


@login_required
@never_cache
def student_notifications(request):
    if account_role(request.user) != "student":
        return JsonResponse({"count": 0, "items": []}, status=403)
    replies = TeacherReply.objects.filter(response__user=request.user, response__lesson__deleted_at__isnull=True,
                                         student_read_at__isnull=True).select_related("response__lesson").order_by("-pk")
    return JsonResponse({"count": replies.count(), "items": [
        {"id": r.pk, "title": r.response.lesson.title, "preview": r.message[:120],
         "url": reverse("student", args=[r.response.lesson.code]) + "#teacher-replies"} for r in replies[:5]
    ]})
