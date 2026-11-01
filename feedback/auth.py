import hashlib
from datetime import timedelta
from django.contrib.auth.views import LoginView
from django.db import transaction
from django.utils import timezone
from .models import LoginThrottle


class TeacherLoginView(LoginView):
    template_name = "login.html"
    window = timedelta(minutes=10)
    limit = 5

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
