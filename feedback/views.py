import csv
from io import BytesIO
from collections import Counter
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.http import HttpResponse, HttpResponseBadRequest, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST
from .forms import JoinForm, LessonForm, ResponseForm
from .models import Lesson, Response, ResponseEvent, AccountProfile, ClassroomMembership, TeacherReply, QuestionAttachment
from .roles import account_role, teacher_required, managed_lessons, is_developer
from .learning import content_context, feedback_payload, reply_payload
from .insights import keyword_insights

STATUSES = [
    {"value": "green", "label": "听懂了", "description": "思路清楚，可以继续", "symbol": "✓"},
    {"value": "yellow", "label": "有点疑惑", "description": "大致理解，想再听一遍", "symbol": "?"},
    {"value": "red", "label": "需要帮助", "description": "暂时跟不上，请慢一点", "symbol": "!"},
]


@never_cache
def health(request):
    from django.db import connection
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
    return HttpResponse("ok", content_type="text/plain")


def home(request):
    return render(request, "home.html", {"form": JoinForm()})


@require_POST
def join(request):
    data = request.POST.copy()
    data["code"] = data.get("code", "").strip().upper()
    form = JoinForm(data)
    if form.is_valid():
        lesson = Lesson.objects.filter(code=form.cleaned_data["code"], deleted_at__isnull=True).first()
        if lesson:
            return redirect("student", code=lesson.code)
        form.add_error("code", "没有找到这个课堂，请向老师确认课堂码。")
    return render(request, "home.html", {"form": form}, status=400)


@teacher_required
def teacher_home(request):
    from django.db.models import Count
    lessons = Lesson.objects.filter(teacher=request.user, deleted_at__isnull=True).annotate(response_count=Count("responses")).order_by("-created_at", "-pk")
    return render(request, "teacher_home.html", {"lessons": lessons})


@teacher_required
def lesson_create(request):
    form = LessonForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        # Retry only a random code collision, without changing any existing lesson.
        for _ in range(5):
            lesson = Lesson(teacher=request.user, **form.cleaned_data)
            try:
                with transaction.atomic():
                    lesson.save()
                return redirect("dashboard", code=lesson.code)
            except IntegrityError:
                continue
        form.add_error(None, "暂时无法生成课堂码，请稍后重试。")
    return render(request, "lesson_form.html", {"form": form})


@login_required
@never_cache
def student_home(request):
    if account_role(request.user) == "teacher":
        return redirect("teacher_home")
    memberships = list(request.user.classroom_memberships.filter(lesson__deleted_at__isnull=True)
                       .select_related("lesson").order_by("-lesson__created_at", "-lesson__pk"))
    responses = {r.lesson_id: r for r in request.user.classroom_responses.all()}
    return render(request, "student_home.html", {
        "classrooms": [{"lesson": m.lesson, "response": responses.get(m.lesson_id)} for m in memberships],
        "form": JoinForm(),
    })


def owned_lesson(request, code):
    return get_object_or_404(managed_lessons(request.user), code=code, deleted_at__isnull=True)


def summary(lesson, page_number=1):
    # Materialize one snapshot, so the chart, notes and denominator agree.
    from django.db.models import F, OuterRef, Q, Subquery
    event = lesson.events.filter(participant=OuterRef("participant")).order_by("-pk").values("pk")[:1]
    # A reply to an earlier question must not hide a student's new question.
    # Replies without an event (legacy/direct replies) must match the current text
    # and have been sent after that feedback was last updated.
    current_replies = TeacherReply.objects.filter(response_id=OuterRef("pk")).filter(
        Q(question_event_id=OuterRef("latest_event_id")) |
        Q(question_event__isnull=True, question_text=OuterRef("note"), created_at__gte=OuterRef("updated_at"))
    ).order_by("-created_at", "-pk")
    responses = list(lesson.responses.select_related("user", "lesson", "block")
        .annotate(latest_event_id=Subquery(event))
        .annotate(answered_at=Subquery(current_replies.values("created_at")[:1]))
        .order_by(F("answered_at").asc(nulls_first=True), "-updated_at", "-pk"))
    counts = Counter(r.status for r in responses)
    total = len(responses)
    rows = [{**s, "count": counts[s["value"]], "percent": round(counts[s["value"]] / total * 100, 1) if total else 0} for s in STATUSES]
    questions = [r for r in responses if r.status in {"yellow", "red"}]
    pages = max(1, (len(questions) + 49) // 50)
    try:
        page = min(pages, max(1, int(page_number)))
    except (TypeError, ValueError):
        page = 1
    selected = questions[(page - 1) * 50:page * 50]
    from django.db.models import prefetch_related_objects
    prefetch_related_objects(selected, "replies__question_event__attachments")
    files = {}
    for attachment in QuestionAttachment.objects.filter(event_id__in=[r.latest_event_id for r in selected]):
        files.setdefault(attachment.event_id, []).append(attachment)
    for response in selected:
        response.question_files = files.get(response.latest_event_id, [])
    notes = [feedback_payload(r) for r in selected]
    from .question_stats import question_statistics
    question_stats = question_statistics(lesson, responses)
    return {
        "total": total, "rows": rows, "notes": notes, "is_open": lesson.is_open,
        "question_groups": [{"status": s["value"], "label": s["label"], "count": counts[s["value"]],
                             "statistics": question_stats[s["value"]],
                             "notes": [n for n in notes if n["status"] == s["value"]]} for s in STATUSES[1:]],
        "expected_count": lesson.expected_count,
        "participation": round(total / lesson.expected_count * 100, 1) if lesson.expected_count else None,
        "updated": timezone.localtime().strftime("%H:%M:%S"),
        "account_count": sum(r.user_id is not None for r in responses),
        "legacy_count": sum(r.user_id is None for r in responses),
        "page": page, "pages": pages,
        "insights": keyword_insights(responses),
    }


@teacher_required
@never_cache
def dashboard(request, code):
    lesson = owned_lesson(request, code)
    data = summary(lesson, request.GET.get("feedback_page", 1))
    return render(request, "dashboard.html", {
        "lesson": lesson, "summary": data,
        "student_url": request.build_absolute_uri(reverse("student", args=[code])),
        "manage_content": True,
        "history_insights": keyword_insights(lesson.events.select_related('block')),
        **content_context(lesson),
    })


@teacher_required
@never_cache
def lesson_stats(request, code):
    return JsonResponse(summary(owned_lesson(request, code), request.GET.get("feedback_page", 1)))


@teacher_required
@never_cache
def lesson_qr(request, code):
    import qrcode
    from qrcode.image.svg import SvgPathImage
    owned_lesson(request, code)
    url = request.build_absolute_uri(reverse("student", args=[code]))
    image = qrcode.make(url, image_factory=SvgPathImage, border=2)
    buffer = BytesIO()
    image.save(buffer)
    return HttpResponse(buffer.getvalue(), content_type="image/svg+xml")


@teacher_required
@require_POST
def toggle_lesson(request, code):
    action = request.POST.get("action")
    if action not in {"open", "close"}:
        return HttpResponseBadRequest("请选择开放或结束课堂。")
    with transaction.atomic():
        lesson = get_object_or_404(managed_lessons(request.user).select_for_update(), code=code, deleted_at__isnull=True)
        lesson.is_open = action == "open"
        lesson.save(update_fields=["is_open"])
    messages.success(request, "课堂已开放，可以继续接收反馈。" if lesson.is_open else "课堂已结束，反馈记录已保留。")
    return redirect("dashboard", code=code)


@login_required
@never_cache
def student(request, code):
    lesson = get_object_or_404(Lesson, code=code.upper(), deleted_at__isnull=True)
    if account_role(request.user) == "teacher":
        if lesson.teacher_id != request.user.pk and not is_developer(request.user):
            raise Http404
        if request.method == "POST":
            return render(request, "role_required.html", {"student_only": True}, status=403)
        return render(request, "student.html", {"lesson": lesson, "teacher_preview": True, **content_context(lesson)})
    profile, _ = AccountProfile.objects.get_or_create(user=request.user)
    ClassroomMembership.objects.get_or_create(lesson=lesson, student=request.user)
    participant = profile.participant
    current = lesson.responses.filter(user=request.user).first()
    error = None
    selected = current.status if current else ""
    note = current.note if current else ""
    real_name = current.real_name if current and current.real_name else profile.real_name
    student_number = current.student_number if current and current.student_number else profile.student_number
    form = ResponseForm(lesson=lesson, initial={'block': current.block_id if current else None})
    if request.method == "POST":
        form = ResponseForm(request.POST, request.FILES, lesson=lesson)
        selected = request.POST.get("status", "")
        note = request.POST.get("note", "")
        real_name = request.POST.get("real_name", "")
        student_number = request.POST.get("student_number", "")
        if not lesson.is_open:
            error = "本次课堂已结束，暂时不能修改反馈。"
        elif not form.is_valid():
            error = "请检查姓名、学号、学习状态和附件；问题文字最多3000字。"
        else:
            with transaction.atomic():
                # Serialize closure and writes where the database supports row locks.
                locked = Lesson.objects.select_for_update().get(pk=lesson.pk)
                if not locked.is_open or locked.deleted_at:
                    error = "本次课堂已结束，暂时不能修改反馈。"
                else:
                    data = form.cleaned_data.copy()
                    uploads = data.pop('attachments')
                    response, created = Response.objects.get_or_create(
                        lesson=locked, user=request.user, defaults={"participant": participant, **data},
                    )
                    latest = locked.events.filter(participant=participant).order_by('-pk').first()
                    answered = response.replies.filter(question_event=latest).exists() if latest else False
                    if not answered:
                        answered = response.replies.filter(question_event__isnull=True, question_text=response.note,
                                                           created_at__gte=response.updated_at).exists()
                    if created or answered or uploads or any(getattr(response, key) != value for key, value in data.items()):
                        if not created:
                            for key, value in data.items():
                                setattr(response, key, value)
                            response.save(update_fields=[*data, "updated_at"])
                        event = ResponseEvent.objects.create(lesson=locked, participant=participant, user=request.user,
                            block_title=str(data['block']) if data['block'] else '', **data)
                        saved = []
                        try:
                            for uploaded in uploads:
                                attachment = QuestionAttachment(event=event, file=uploaded, original_name=uploaded.name,
                                    size=uploaded.size, content_type=uploaded.inspected_type, is_image=uploaded.inspected_image)
                                saved.append(attachment)
                                attachment.save()
                        except Exception:
                            for attachment in saved:
                                if attachment.file._committed:
                                    attachment.file.delete(save=False)
                            raise
                    AccountProfile.objects.filter(pk=profile.pk).update(real_name=data["real_name"], student_number=data["student_number"])
            if not error:
                messages.success(request, "反馈已送达老师。理解程度变化时，您可以再次更新。")
                return redirect("student", code=lesson.code)
    return render(request, "student.html", {
        "lesson": lesson, "statuses": STATUSES, "current": current,
        "selected": selected, "note": note, "error": error,
        "real_name": real_name, "student_number": student_number,
        "question_form": form,
        "question_history": Paginator(
            lesson.events.filter(user=request.user).prefetch_related('attachments').order_by('-pk'), 20).get_page(request.GET.get('questions_page')),
        "replies": [reply_payload(r) for r in TeacherReply.objects.filter(response__lesson=lesson, response__user=request.user).select_related('question_event').prefetch_related('question_event__attachments')],
        **content_context(lesson),
    }, status=400 if error else 200)


def csv_safe(value):
    value = str(value)
    # Spreadsheet formulas may be triggered even after leading whitespace.
    return "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) else value


@teacher_required
@never_cache
def export_csv(request, code):
    lesson = owned_lesson(request, code)
    history = request.GET.get("history") == "1"
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="classroom-{code}-{"history" if history else "latest"}.csv"'
    response.write("\ufeff")
    writer = csv.writer(response)
    writer.writerow(["课程", "课堂", "课堂码", "统计类型", "课堂内随机编号", "理解程度", "补充说明", "时间（北京时间）", "反馈来源", "姓名", "学号"])
    records = lesson.events.order_by("created_at", "pk") if history else lesson.responses.order_by("updated_at", "pk")
    # Export only lesson-scoped numbering, never the browser's cross-lesson UUID.
    participants = {}
    for record in records:
        number = participants.setdefault(record.participant, len(participants) + 1)
        when = record.created_at if history else record.updated_at
        writer.writerow([csv_safe(lesson.course), csv_safe(lesson.title), code,
                         "变更历史" if history else "当前状态", number,
                         record.get_status_display(), csv_safe(record.note),
                         timezone.localtime(when).strftime("%Y-%m-%d %H:%M:%S"),
                         "学生账号反馈" if record.user_id is not None else "历史不记名反馈",
                         csv_safe(record.real_name), csv_safe(record.student_number)])
    return response
