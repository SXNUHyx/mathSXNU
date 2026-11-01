"""Local Docker Compose check with isolated volumes, fake data and loopback ports.

Uses the already-built mathsxnu-classroom:local image. Does not issue real TLS
certificates or publish a classroom website. Requires Docker Compose v2.
"""
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import tempfile
import time
from urllib.request import Request, ProxyHandler, build_opener
from urllib.error import HTTPError
import uuid

ROOT = Path(__file__).resolve().parent.parent


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def main():
    project = "classroom-smoke-" + uuid.uuid4().hex[:8]
    http_port, https_port = free_port(), free_port()
    env = {**os.environ,
           "DJANGO_SECRET_KEY": secrets.token_urlsafe(64),
           "CLASSROOM_DOMAIN": "classroom.test",
           "CLASSROOM_HTTP_BIND": f"127.0.0.1:{http_port}",
           "CLASSROOM_HTTPS_BIND": f"127.0.0.1:{https_port}"}
    # Target only the local managed daemon, never another saved Docker context.
    for key in ["DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_TLS", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH"]:
        env.pop(key, None)
    with tempfile.TemporaryDirectory(prefix="classroom-compose-") as tmp:
        override = Path(tmp) / "override.json"
        override.write_text(json.dumps({"services": {
            "web": {"environment": {"DJANGO_SSL_REDIRECT": "0"}},
            "gateway": {"environment": {"CLASSROOM_DOMAIN": "http://classroom.test"}},
        }}))
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
                "l=Lesson.objects.create(teacher=u,title='容器持久化演示')\n"
                "Response.objects.create(lesson=l,participant=uuid.uuid4(),status='red')\n"
            )
            run("exec", "-T", "web", "python", "manage.py", "shell", input=seed, text=True, stdout=subprocess.DEVNULL)
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
            run("exec", "-T", "web", "python", "manage.py", "backup_classroom", "--output", "/data/backup-smoke.sqlite3")
            print("通过：Compose服务、HTTP反向代理、静态文件、健康检查、容器重启后数据持久化、容器内备份。未申请真实域名TLS证书。")
        finally:
            # Only our random test project's synthetic volumes are removed.
            subprocess.run([*base, "down", "-v"], cwd=ROOT, env=env, check=False)


if __name__ == "__main__":
    main()
