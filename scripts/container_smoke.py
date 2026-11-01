"""Local Docker Compose check with isolated volumes, fake data and loopback ports.

Uses the already-built mathsxnu-classroom:local image. Does not issue real TLS
certificates or publish a classroom website. Requires Docker Compose v2.
"""
import json
import argparse
import os
from pathlib import Path
import secrets
import socket
import subprocess
import tempfile
import time
from urllib.request import Request, ProxyHandler, HTTPCookieProcessor, build_opener
from urllib.parse import urlencode
from http.cookiejar import CookieJar
import re
from urllib.error import HTTPError
import uuid

ROOT = Path(__file__).resolve().parent.parent


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--upgrade-from", help="Optional old image for an isolated, real upgrade rehearsal")
    parser.add_argument("--http-trial", action="store_true", help="Validate explicit HTTP access and persistent login cookies")
    args = parser.parse_args()
    project = "classroom-smoke-" + uuid.uuid4().hex[:8]
    http_port, https_port = free_port(), free_port()
    env = {**os.environ,
           "DJANGO_SECRET_KEY": secrets.token_urlsafe(64),
           "CLASSROOM_DOMAIN": "classroom.test",
           "CLASSROOM_HTTP_BIND": f"127.0.0.1:{http_port}",
           "CLASSROOM_HTTPS_BIND": f"127.0.0.1:{https_port}"}
    if args.http_trial:
        env.update({"CLASSROOM_SCHEME": "http", "CLASSROOM_ALLOW_INSECURE_HTTP": "1"})
    # Target only the local managed daemon, never another saved Docker context.
    for key in ["DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_TLS", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH"]:
        env.pop(key, None)
    with tempfile.TemporaryDirectory(prefix="classroom-compose-") as tmp:
        override = Path(tmp) / "override.json"
        overrides = {"services": {
            "web": {"image": args.upgrade_from or "mathsxnu-classroom:local", "environment": {"DJANGO_SSL_REDIRECT": "0"}},
            "gateway": {"environment": {"CLASSROOM_DOMAIN": "http://classroom.test"}},
        }}
        override.write_text(json.dumps(overrides))
        base = ["docker", "--host=unix:///var/run/docker.sock", "compose", "-p", project,
                "-f", str(ROOT / "compose.yaml"), "-f", str(override)]
        def run(*args, **kwargs):
            return subprocess.run([*base, *args], cwd=ROOT, env=env, check=True, **kwargs)
        try:
            run("config", "--quiet")  # Never print the expanded secret-bearing configuration.
            run("up", "-d", "--no-build", "--wait", "--wait-timeout", "120")
            opener = build_opener(ProxyHandler({}))  # Loopback only.
            for path, marker in [("/", "课堂信号"), ("/health/", "ok"), ("/static/app.css", ":root")]:
                req = Request(f"http://127.0.0.1:{http_port}{path}", headers={"Host": "classroom.test"})
                try:
                    with opener.open(req, timeout=10) as response:
                        assert marker in response.read().decode(), path
                except HTTPError as exc:
                    print("测试HTTP错误：", path, exc.code, exc.read().decode(errors="replace")[:600])
                    raise
            seed = (
                "from django.contrib.auth import get_user_model\n"
                "from feedback.models import Lesson,Response\n"
                "import uuid\n"
                "u=get_user_model().objects.create_user('container_test')\n"
                "from django.apps import apps\n"
                "try:\n"
                "    Profile=apps.get_model('feedback','AccountProfile')\n"
                "except LookupError:\n"
                "    Profile=None\n"
                "if Profile:\n"
                "    Profile.objects.create(user=u,role='teacher')\n"
                "l=Lesson.objects.create(teacher=u,title='容器持久化演示')\n"
                "Response.objects.create(lesson=l,participant=uuid.uuid4(),status='red')\n"
            )
            run("exec", "-T", "web", "python", "manage.py", "shell", input=seed, text=True, stdout=subprocess.DEVNULL)
            course_file_seed = (
                "from feedback.models import Lesson,KnowledgeBlock,CourseMaterial\n"
                "from django.core.files.base import ContentFile\n"
                "lesson=Lesson.objects.get()\n"
                "block=KnowledgeBlock.objects.create(lesson=lesson,kind='difficult',title='持久知识点',body=r'\\(x^2\\)')\n"
                "CourseMaterial.objects.create(lesson=lesson,block=block,title='持久课程文件',file=ContentFile(b'%PDF-1.7\\nfixture',name='fixture.pdf'),original_name='fixture.pdf',content_type='application/pdf',size=16,is_image=False)\n"
            )
            has_old_materials = False
            if args.upgrade_from:
                probe = run("exec", "-T", "web", "python", "manage.py", "shell", input="from django.apps import apps\nprint('HAS_MATERIALS' if apps.get_model('feedback','Lesson')._meta.apps.all_models['feedback'].get('coursematerial') else 'NO_MATERIALS')\n",text=True,capture_output=True)
                has_old_materials = 'HAS_MATERIALS' in probe.stdout
                if has_old_materials:
                    run("exec", "-T", "web", "python", "manage.py", "shell", input=course_file_seed,text=True,stdout=subprocess.DEVNULL)
                run("stop", "gateway")
                run("exec", "-T", "web", "python", "manage.py", "backup_classroom", "--output", "/data/pre-upgrade.sqlite3")
                if has_old_materials:
                    run("exec", "-T", "web", "python", "manage.py", "backup_course_files", "--output", "/data/pre-upgrade-materials.tar.gz")
                overrides["services"]["web"]["image"] = "mathsxnu-classroom:local"
                override.write_text(json.dumps(overrides))
                run("up", "-d", "--no-build", "--wait", "--wait-timeout", "120")
                run("exec", "-T", "web", "python", "manage.py", "shell", input="from feedback.models import AccountProfile,Response\nassert AccountProfile.objects.get(user__username='container_test').role=='teacher'\nassert Response.objects.get().user_id is None\n", text=True, stdout=subprocess.DEVNULL)
                print("旧版升级通过：教师身份与历史反馈保留；既有资料（如有）保留。")
            if not has_old_materials:
                run("exec", "-T", "web", "python", "manage.py", "shell", input=course_file_seed, text=True, stdout=subprocess.DEVNULL)
            run("restart", "web")
            for _ in range(50):
                try:
                    with opener.open(Request(f"http://127.0.0.1:{http_port}/health/", headers={"Host": "classroom.test"}), timeout=2) as r:
                        assert r.read() == b"ok"
                    break
                except OSError:
                    time.sleep(.2)
            else:
                raise RuntimeError("容器重启后未恢复健康状态")
            run("exec", "-T", "web", "python", "manage.py", "shell", input="from feedback.models import Lesson,Response\nassert Lesson.objects.get().title=='容器持久化演示'\nassert Response.objects.get().status=='red'\n", text=True, stdout=subprocess.DEVNULL)
            run("exec", "-T", "web", "python", "manage.py", "shell", input="from feedback.models import CourseMaterial,KnowledgeBlock\nfrom django.conf import settings\nfrom pathlib import Path\nm=CourseMaterial.objects.get()\nassert str(settings.MEDIA_ROOT)=='/data/media'\nassert Path(m.file.path).read_bytes()==b'%PDF-1.7\\nfixture'\nassert m.block.kind=='difficult'\nfrom feedback.learning import content_context\nassert content_context(m.lesson)['content_sections'][2]['blocks'][0]['materials'][0].pk==m.pk\nassert KnowledgeBlock.objects.get().title=='持久知识点'\n",text=True,stdout=subprocess.DEVNULL)
            if args.http_trial:
                for role in ["teacher", "student"]:
                    jar = CookieJar()
                    client = build_opener(ProxyHandler({}), HTTPCookieProcessor(jar))
                    base_url = f"http://127.0.0.1:{http_port}"
                    headers = {"Host": "classroom.test", "Origin": "http://classroom.test"}
                    username = "http_container_" + role
                    password = secrets.token_urlsafe(24) + "!A9"
                    def get(path):
                        with client.open(Request(base_url + path, headers=headers), timeout=10) as response:
                            return response.geturl(), response.read().decode()
                    def post(path, fields):
                        with client.open(Request(base_url + path, data=urlencode(fields).encode(), headers=headers), timeout=10) as response:
                            return response.geturl(), response.read().decode()
                    def token(html):
                        return re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', html).group(1)
                    _, html = get(f"/accounts/register/{role}/")
                    url, html = post(f"/accounts/register/{role}/", {"username": username, "password1": password, "password2": password, "csrfmiddlewaretoken": token(html)})
                    assert url.endswith(f"/{role}/"), "HTTP signup session did not persist"
                    assert any(c.name == "sessionid" and not c.secure for c in jar)
                    post("/accounts/logout/", {"csrfmiddlewaretoken": token(html)})
                    _, html = get("/accounts/login/")
                    url, _ = post("/accounts/login/", {"username": username, "password": password, "csrfmiddlewaretoken": token(html)})
                    assert url.endswith(f"/{role}/"), "HTTP login session did not persist"
                run("exec", "-T", "web", "python", "manage.py", "check_login_access")
                print("HTTP容器验证通过：师生注册、退出后重新登录、会话Cookie均正确，不再回到登录页。")
            run("exec", "-T", "web", "python", "manage.py", "backup_classroom", "--output", "/data/backup-smoke.sqlite3")
            run("exec", "-T", "web", "python", "manage.py", "backup_course_files", "--output", "/data/materials-smoke.tar.gz")
            archive = Path(tmp) / "materials-smoke.tar.gz"
            run("cp", "web:/data/materials-smoke.tar.gz", str(archive))
            import tarfile
            with tarfile.open(archive) as source:
                names = source.getnames()
                assert len(names) == 1 and names[0].startswith("media/")
                assert source.extractfile(names[0]).read() == b"%PDF-1.7\nfixture"
            print("通过：Compose服务、HTTP反向代理、静态文件、健康检查、容器重启后数据持久化、容器内备份。未申请真实域名TLS证书。")
        finally:
            # Only our random test project's synthetic volumes are removed.
            subprocess.run([*base, "down", "-v"], cwd=ROOT, env=env, check=False)


if __name__ == "__main__":
    main()
