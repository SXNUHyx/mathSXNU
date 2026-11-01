from urllib.parse import urlsplit
from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "显示登录访问协议与Cookie设置，不显示密钥、密码或Cookie值。"

    def handle(self, *args, **options):
        try:
            origin = urlsplit(settings.PUBLIC_ORIGIN)
            host = origin.hostname or ""
            display = f"{origin.scheme}://{host}" if origin.scheme in {"http", "https"} and host else "未配置有效地址"
            if host and origin.port:
                display += f":{origin.port}"
        except ValueError:
            origin, display = None, "未配置有效地址"
        self.stdout.write(f"网站地址：{display}")
        self.stdout.write(f"HTTP试用模式：{'已启用' if settings.ALLOW_INSECURE_HTTP else '未启用'}")
        self.stdout.write(f"登录Cookie仅限HTTPS：{settings.SESSION_COOKIE_SECURE}")
        self.stdout.write(f"CSRF Cookie仅限HTTPS：{settings.CSRF_COOKIE_SECURE}")
        self.stdout.write(f"强制HTTPS跳转：{settings.SECURE_SSL_REDIRECT}")
        if origin and origin.scheme == "http" and (settings.SESSION_COOKIE_SECURE or settings.CSRF_COOKIE_SECURE or settings.SECURE_SSL_REDIRECT):
            self.stdout.write(self.style.ERROR("配置不一致：HTTP地址与安全登录设置冲突，请统一配置访问模式。"))
        elif settings.ALLOW_INSECURE_HTTP:
            self.stdout.write(self.style.WARNING("仅供功能测试：HTTP不加密密码和反馈，正式教学请切换HTTPS。"))
