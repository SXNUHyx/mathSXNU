import os
import secrets
from pathlib import Path
from urllib.parse import urlsplit
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent
ASSET_VERSION = "20261102-user-management"
CSRF_FAILURE_VIEW = 'feedback.management_views.csrf_failure'
MATHAI_PROVIDERS = {
    'deepseek': {'key':os.environ.get('DEEPSEEK_API_KEY',''), 'model':os.environ.get('DEEPSEEK_MODEL','deepseek-chat')},
    'doubao': {'key':os.environ.get('DOUBAO_API_KEY',''), 'model':os.environ.get('DOUBAO_MODEL','')},
    'kimi': {'key':os.environ.get('KIMI_API_KEY',''), 'model':os.environ.get('KIMI_MODEL','moonshot-v1-8k')},
}
MATHAI_DAILY_USER_LIMIT = max(1,min(1000,int(os.environ.get('MATHAI_DAILY_USER_LIMIT','30'))))
MATHAI_DAILY_GLOBAL_LIMIT = max(1,min(100000,int(os.environ.get('MATHAI_DAILY_GLOBAL_LIMIT','1000'))))
# Optional licensed MathType service base URI; no demo service is enabled.
MATHTYPE_SERVICE_URI = os.environ.get("MATHTYPE_SERVICE_URI", "").strip()
MATHTYPE_SERVICE_SERVER = os.environ.get("MATHTYPE_SERVICE_SERVER", "java").strip()
if MATHTYPE_SERVICE_URI:
    service_url = urlsplit(MATHTYPE_SERVICE_URI)
    relative = MATHTYPE_SERVICE_URI.startswith("/") and not MATHTYPE_SERVICE_URI.startswith("//")
    if (not (relative or (service_url.scheme == "https" and service_url.hostname))
            or service_url.username or service_url.password or service_url.query or service_url.fragment
            or "\\" in MATHTYPE_SERVICE_URI or any(c.isspace() for c in MATHTYPE_SERVICE_URI)
            or not MATHTYPE_SERVICE_URI.endswith("/")
            or MATHTYPE_SERVICE_SERVER not in {"java", "php"}):
        raise ImproperlyConfigured("MathType需要不含密钥的HTTPS或同源服务根路径（以/结尾），服务类型为java或php。")
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
ALLOW_INSECURE_HTTP = os.environ.get("DJANGO_ALLOW_INSECURE_HTTP", "0") == "1"
PUBLIC_ORIGIN = os.environ.get("DJANGO_PUBLIC_ORIGIN", "")
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    if not DEBUG:
        raise RuntimeError("生产环境必须设置 DJANGO_SECRET_KEY。")
    local = BASE_DIR / ".local"
    local.mkdir(mode=0o700, exist_ok=True)
    secret_file = local / "secret_key"
    try:
        with open(secret_file, "x", opener=lambda p, f: os.open(p, f, 0o600)) as f:
            f.write(secrets.token_urlsafe(50))
    except FileExistsError:
        pass
    SECRET_KEY = secret_file.read_text().strip()

ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,[::1]").split(",")
CSRF_TRUSTED_ORIGINS = list(filter(None, os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",")))
INSTALLED_APPS = [
    "django.contrib.auth", "django.contrib.contenttypes", "django.contrib.sessions",
    "django.contrib.messages", "django.contrib.staticfiles", "feedback",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "feedback.middleware.AuthenticationTransportMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "mathsxnu.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [BASE_DIR / "templates"], "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
        "feedback.roles.account_context",
        "feedback.navigation.authentication_context",
    ]},
}]
WSGI_APPLICATION = "mathsxnu.wsgi.application"
DATABASES = {"default": {
    "ENGINE": "django.db.backends.sqlite3",
    "NAME": os.environ.get("DJANGO_DB_PATH", str(BASE_DIR / ".local" / "db.sqlite3")),
    "OPTIONS": {"timeout": 20, "transaction_mode": "IMMEDIATE"},
}}
# The directory also exists when a production secret is injected.
Path(DATABASES["default"]["NAME"]).parent.mkdir(parents=True, exist_ok=True)
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LANGUAGE_CODE = "zh-hans"
TIME_ZONE = "Asia/Shanghai"
USE_I18N = True
USE_TZ = True
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_ROOT = Path(os.environ.get("DJANGO_MEDIA_ROOT", str(BASE_DIR / ".local" / "media")))
FILE_UPLOAD_MAX_MEMORY_SIZE = 2_500_000
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "teacher_home"
LOGOUT_REDIRECT_URL = "home"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = not (DEBUG or ALLOW_INSECURE_HTTP)
CSRF_COOKIE_SECURE = not (DEBUG or ALLOW_INSECURE_HTTP)
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
if os.environ.get("DJANGO_TRUST_PROXY") == "1":
    # Enable only behind a trusted proxy that overwrites this header.
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = os.environ.get("DJANGO_SSL_REDIRECT", "0" if DEBUG or ALLOW_INSECURE_HTTP else "1") == "1"
SECURE_REDIRECT_EXEMPT = [r"^health/$"]
