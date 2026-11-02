"""Shared, role-aware destinations for login and signup."""
from urllib.parse import urlsplit
from django.urls import Resolver404, resolve, reverse
from django.utils.http import url_has_allowed_host_and_scheme
from .models import Lesson
from .roles import account_role

PENDING_CLASSROOM = "pending_classroom_url"
LANDING_VIEWS = {"student", "student_home", "teacher_home", "lesson_create", "dashboard",
                 'developer_home','developer_user_new','developer_user','developer_user_action','developer_audit','password_change'}


def landing_match(request, target):
    if not target or not isinstance(target, str) or not url_has_allowed_host_and_scheme(
        target, allowed_hosts={request.get_host()}, require_https=request.is_secure(),
    ):
        return None
    try:
        match = resolve(urlsplit(target).path)
    except (Resolver404, ValueError):
        return None
    return match if match.url_name in LANDING_VIEWS else None


def pending_classroom(request):
    target = request.session.get(PENDING_CLASSROOM, "")
    match = landing_match(request, target)
    if match and match.url_name == "student":
        code = match.kwargs["code"].upper()
        if Lesson.objects.filter(code=code, deleted_at__isnull=True).exists():
            return reverse("student", args=[code])
    if target:
        request.session.pop(PENDING_CLASSROOM, None)
    return ""


def remember_classroom(request):
    target = request.POST.get("next") or request.GET.get("next", "")
    match = landing_match(request, target)
    if match and match.url_name == "student":
        code = match.kwargs["code"].upper()
        if Lesson.objects.filter(code=code, deleted_at__isnull=True).exists():
            request.session[PENDING_CLASSROOM] = reverse("student", args=[code])


def authentication_next(request):
    target = request.POST.get("next") or request.GET.get("next", "")
    match = landing_match(request, target)
    if match:
        return reverse(match.url_name, kwargs=match.kwargs)
    return pending_classroom(request)


def authentication_context(request):
    return {"auth_next": authentication_next(request)}


def authentication_destination(request, user):
    role = account_role(user)
    candidates = [authentication_next(request), pending_classroom(request)]
    request.session.pop(PENDING_CLASSROOM, None)
    for target in candidates:
        match = landing_match(request, target)
        if not match:
            continue
        name = match.url_name
        if name=='password_change':
            return reverse(name)
        if name.startswith('developer_'):
            if user.is_active and user.is_staff and user.is_superuser:
                return reverse(name,kwargs=match.kwargs)
            continue
        code = match.kwargs.get("code", "").upper()
        if role == "teacher":
            if name in {"teacher_home", "lesson_create"}:
                return reverse(name)
            if name in {"student", "dashboard"} and Lesson.objects.filter(code=code, teacher=user, deleted_at__isnull=True).exists():
                return reverse("dashboard", args=[code])
        elif name == "student_home":
            return reverse("student_home")
        elif name == "student" and Lesson.objects.filter(code=code, deleted_at__isnull=True).exists():
            return reverse("student", args=[code])
    return reverse("teacher_home" if role == "teacher" else "student_home")
