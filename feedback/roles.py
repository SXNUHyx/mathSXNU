from functools import wraps
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from .models import AccountProfile


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
    return {"account_role": account_role(request.user)}


def teacher_required(view):
    @login_required
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if account_role(request.user) != AccountProfile.Role.TEACHER:
            return render(request, "role_required.html", status=403)
        return view(request, *args, **kwargs)
    return wrapped
