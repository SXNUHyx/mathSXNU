from urllib.parse import urlsplit
from django.conf import settings
from django.shortcuts import render
from django.urls import reverse


class AuthenticationTransportMiddleware:
    """Explain transport/cookie mismatches instead of accepting unusable logins."""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        auth_page = request.path == reverse("login") or request.path.startswith("/accounts/register/")
        if auth_page and not request.is_secure() and settings.SESSION_COOKIE_SECURE:
            origin = urlsplit(settings.PUBLIC_ORIGIN)
            secure_login_url = None
            if origin.scheme == "https" and origin.netloc and not origin.username and not origin.password:
                secure_login_url = f"https://{origin.netloc}{reverse('login')}"
            return render(request, "https_required.html", {"secure_login_url": secure_login_url}, status=400)
        return self.get_response(request)
