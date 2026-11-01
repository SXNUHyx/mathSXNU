import hashlib
from datetime import timedelta
from django.contrib.auth.views import LoginView
from django.contrib.auth import login
from django.contrib import messages
from django.db import IntegrityError, transaction
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.utils import timezone
from .models import LoginThrottle, AccountProfile
from .forms import RegistrationForm, PlatformAuthenticationForm
from .navigation import authentication_destination, authentication_next, remember_classroom


class TeacherLoginView(LoginView):
    template_name = "login.html"
    authentication_form = PlatformAuthenticationForm
    redirect_authenticated_user = True
    window = timedelta(minutes=10)
    limit = 5

    def dispatch(self, request, *args, **kwargs):
        remember_classroom(request)
        return super().dispatch(request, *args, **kwargs)

    def get_success_url(self):
        return authentication_destination(self.request, self.request.user)

    def throttle_key(self):
        username = self.request.POST.get("username", "").strip().casefold()
        return hashlib.sha256(username.encode()).hexdigest()

    def post(self, request, *args, **kwargs):
        blocked = LoginThrottle.objects.filter(
            key=self.throttle_key(), failures__gte=self.limit,
            window_started__gt=timezone.now() - self.window,
        ).exists()
        if blocked:
            return self.render_to_response(
                self.get_context_data(form=self.get_form(), login_throttled=True), status=429,
            )
        return super().post(request, *args, **kwargs)

    def form_invalid(self, form):
        with transaction.atomic():
            throttle, _ = LoginThrottle.objects.select_for_update().get_or_create(key=self.throttle_key())
            if throttle.window_started <= timezone.now() - self.window:
                throttle.failures = 0
                throttle.window_started = timezone.now()
            throttle.failures += 1
            throttle.save()
        return super().form_invalid(form)

    def form_valid(self, form):
        LoginThrottle.objects.filter(key=self.throttle_key()).delete()
        return super().form_valid(form)


def safe_next(request):
    return authentication_next(request)


@never_cache
def registration_choice(request):
    remember_classroom(request)
    return render(request, "register_choice.html", {"next": safe_next(request)})


@never_cache
def register(request, role):
    remember_classroom(request)
    if request.user.is_authenticated:
        messages.info(request, "您已登录。若要注册另一个账号，请先退出。")
        return redirect(authentication_destination(request, request.user))
    # Role is fixed by the URL configuration; POST data cannot grant admin flags.
    form = RegistrationForm(request.POST if request.method == "POST" else None)
    if request.method == "POST":
        user = None
        try:
            if form.is_valid():
                # Hash before acquiring the database's write lock during signup bursts.
                user = form.save(commit=False)
                with transaction.atomic():
                    user.save()
                    AccountProfile.objects.create(user=user, role=role)
        except IntegrityError:
            form.add_error("username", "这个用户名已被使用，请换一个。")
            user = None
        if user is not None:
            login(request, user, backend="django.contrib.auth.backends.ModelBackend")
            messages.success(request, "注册成功，已为您登录。")
            return redirect(authentication_destination(request, user))
    return render(request, "register.html", {"form": form, "role": role, "next": safe_next(request)})
