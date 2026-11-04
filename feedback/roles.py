from functools import wraps
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from .models import AccountProfile


def is_developer(user):
    return bool(user.is_authenticated and user.is_active and user.is_staff and user.is_superuser)


def managed_lessons(user):
    """Course owners and active developer administrators may manage lessons."""
    from .models import Lesson
    lessons = Lesson.objects.all()
    return lessons if is_developer(user) else lessons.filter(teacher=user)


def account_role(user):
    if not user.is_authenticated:
        return None
    if user.is_superuser or user.is_staff:
        return AccountProfile.Role.TEACHER
    try:
        return user.account_profile.role
    except AccountProfile.DoesNotExist:
        return AccountProfile.Role.STUDENT


def account_context(request):
    return {"account_role": account_role(request.user), "http_trial": settings.ALLOW_INSECURE_HTTP,
            "asset_version": settings.ASSET_VERSION,
            "mathtype_service_uri": settings.MATHTYPE_SERVICE_URI,
            "mathtype_service_server": settings.MATHTYPE_SERVICE_SERVER,
            "developer_access": is_developer(request.user)}


def teacher_required(view):
    @login_required
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if account_role(request.user) != AccountProfile.Role.TEACHER:
            return render(request, "role_required.html", status=403)
        return view(request, *args, **kwargs)
    return wrapped
