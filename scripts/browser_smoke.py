"""Optional real-browser smoke test. Uses a separate temporary database.

Run with a Python interpreter that has Playwright installed:
  python scripts/browser_smoke.py
Default Chromium path: /usr/bin/chromium (override CHROMIUM_PATH).
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
from urllib.request import urlopen

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
PYTHON = str(ROOT / ".venv/bin/python")
ARTIFACTS = ROOT / ".local/screenshots"
ARTIFACTS.mkdir(parents=True, exist_ok=True)
password = secrets.token_urlsafe(24)
parser = argparse.ArgumentParser()
parser.add_argument("--http-production", action="store_true", help="Use a non-localhost HTTP origin with explicit trial mode")
args = parser.parse_args()

with tempfile.TemporaryDirectory(prefix="mathsxnu-browser-") as tmp:
    env = {**os.environ, "DJANGO_DB_PATH": str(Path(tmp) / "test.sqlite3"), "DJANGO_DEBUG": "1"}
    if args.http_production:
        env.update({"DJANGO_DEBUG": "0", "DJANGO_SECRET_KEY": secrets.token_urlsafe(64),
                    "DJANGO_ALLOW_INSECURE_HTTP": "1", "DJANGO_SSL_REDIRECT": "0",
                    "DJANGO_ALLOWED_HOSTS": "classroom.test,127.0.0.1"})
    subprocess.run([PYTHON, "manage.py", "migrate", "--noinput"], cwd=ROOT, env=env, check=True, stdout=subprocess.DEVNULL)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    base = f"http://{'classroom.test' if args.http_production else '127.0.0.1'}:{port}"
    env["DJANGO_PUBLIC_ORIGIN"] = base
    # Gunicorn + collected assets exercise the deployment path, not just Django's test client.
    server = subprocess.Popen([str(ROOT / ".venv/bin/gunicorn"), "mathsxnu.wsgi:application", "--bind", f"127.0.0.1:{port}", "--workers", "1", "--threads", "4"], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(50):
            try:
                urlopen(f"http://127.0.0.1:{port}/health/", timeout=1).close()
                break
            except OSError:
                if server.poll() is not None:
                    raise RuntimeError("Smoke-test server exited before startup")
                time.sleep(.1)
        with sync_playwright() as p:
            browser_args = ["--no-sandbox"]
            browser_options = {}
            if args.http_production:
                browser_args.append("--host-resolver-rules=MAP classroom.test 127.0.0.1")
                proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")
                if proxy:
                    # Only the synthetic hostname mapped to loopback avoids the proxy.
                    browser_options["proxy"] = {"server": proxy, "bypass": "classroom.test,127.0.0.1,localhost"}
            browser = p.chromium.launch(executable_path=os.environ.get("CHROMIUM_PATH", "/usr/bin/chromium"), args=browser_args, **browser_options)
            errors = []
            teacher_context = browser.new_context(viewport={"width": 1440, "height": 1000})
            teacher = teacher_context.new_page()
            teacher.on("pageerror", lambda e: errors.append(str(e)))
            teacher.goto(base)
            teacher.screenshot(path=str(ARTIFACTS / "home-desktop.png"), full_page=True)
            teacher.get_by_role("link", name="教师注册", exact=True).click()
            teacher.screenshot(path=str(ARTIFACTS / "teacher-register-desktop.png"), full_page=True)
            teacher.get_by_label("用户名", exact=True).fill("browser_teacher")
            teacher.get_by_label("密码", exact=True).fill(password)
            teacher.get_by_label("密码确认", exact=True).fill(password)
            teacher.get_by_role("button", name="注册教师账号").click()
            # Already signed in: revisiting login must lead to the classroom portal.
            teacher.goto(base + "/accounts/login/")
            teacher.get_by_role("heading", name="每一个信号，都值得看见。", exact=True).wait_for()
            if args.http_production:
                cookies = teacher_context.cookies(base)
                assert any(c["name"] == "sessionid" and not c["secure"] for c in cookies)
            teacher.get_by_role("button", name="退出", exact=True).click()
            teacher.goto(base + "/accounts/login/")
            teacher.get_by_label("用户名", exact=True).fill("browser_teacher")
            teacher.get_by_label("密码", exact=True).fill(password)
            teacher.get_by_role("button", name="登录", exact=False).click()
            teacher.get_by_role("heading", name="每一个信号，都值得看见。", exact=True).wait_for()
            teacher.get_by_role("link", name="创建我的第一个课堂").click()
            teacher.get_by_label("课程名称").fill("高等数学 · 演示课堂")
            teacher.get_by_label("本次课堂 / 知识点").fill("连续与可导的关系")
            teacher.get_by_label("预计参与人数").fill("40")
            teacher.get_by_role("button", name="创建并获取课堂码").click()
            teacher.wait_for_selector("#dashboard")
            student_url = teacher.locator("#student-link").input_value()
            mobile_context = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
            student = mobile_context.new_page()
            student.on("pageerror", lambda e: errors.append(str(e)))
            student.goto(student_url)
            # Exercise the generic navbar route that used to lose the classroom next URL.
            student.get_by_role("navigation").get_by_role("link", name="注册", exact=True).click()
            student.get_by_role("link", name="我是学生，参与课堂", exact=False).click()
            student.screenshot(path=str(ARTIFACTS / "student-register-mobile.png"), full_page=True)
            student.get_by_label("用户名", exact=True).fill("browser_student")
            student.get_by_label("密码", exact=True).fill(password)
            student.get_by_label("密码确认", exact=True).fill(password)
            student.get_by_role("button", name="注册学生账号").click()
            assert student.url == student_url
            student.get_by_role("radio", name="需要帮助").check()
            student.get_by_label("想让老师多讲一点什么").fill("为什么连续不一定可导？想再看一个反例。")
            student.get_by_role("button", name="把信号送给老师").click()
            student.get_by_role("status").filter(has_text="反馈已送达老师").wait_for()
            student.screenshot(path=str(ARTIFACTS / "student-mobile.png"), full_page=True)
            teacher.wait_for_function("document.querySelector('#count-red').textContent === '1'", timeout=10000)
            teacher.wait_for_timeout(500)  # Let the chart's short CSS transition settle for the screenshot.
            assert teacher.locator("#total").inner_text() == "1"
            # A new browser logged into the same student account sees and updates one response.
            second_context = browser.new_context(viewport={"width": 1366, "height": 900})
            second = second_context.new_page()
            second.goto(student_url)
            second.get_by_label("用户名", exact=True).fill("browser_student")
            second.get_by_label("密码", exact=True).fill(password)
            second.get_by_role("button", name="登录", exact=False).click()
            assert second.url == student_url
            second.get_by_role("radio", name="有点疑惑").check()
            second.get_by_role("button", name="更新我的反馈").click()
            teacher.wait_for_function("document.querySelector('#count-yellow').textContent === '1'", timeout=10000)
            assert teacher.locator("#total").inner_text() == "1"
            second.goto(base + "/teacher/")
            assert second.get_by_role("heading", name="这里需要教师账号").count() == 1
            student.goto(base + "/student/")
            student.get_by_role("heading", name="我的学习", exact=True).wait_for()
            student.goto(student_url)
            assert "为什么连续不一定可导" in teacher.locator("#notes").inner_text()
            teacher.screenshot(path=str(ARTIFACTS / "teacher-desktop.png"), full_page=True)
            student.get_by_role("radio", name="听懂了").check()
            student.get_by_role("button", name="更新我的反馈").click()
            teacher.wait_for_function("document.querySelector('#count-green').textContent === '1'", timeout=10000)
            assert teacher.locator("#total").inner_text() == "1"
            with teacher.expect_download() as download:
                teacher.get_by_role("link", name="导出当前反馈 CSV").click()
            assert download.value.suggested_filename.endswith("latest.csv")
            teacher.get_by_role("button", name="结束本次收集").click()
            student.reload()
            student.get_by_role("heading", name="感谢你的课堂反馈").wait_for()
            assert student.locator('button[type="submit"]').count() == 0
            # Mobile dashboard and homepage must not overflow horizontally.
            teacher.set_viewport_size({"width": 390, "height": 844})
            teacher.screenshot(path=str(ARTIFACTS / "teacher-mobile.png"), full_page=True)
            assert teacher.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            student.goto(base)
            student.screenshot(path=str(ARTIFACTS / "home-mobile.png"), full_page=True)
            assert student.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            assert not errors, errors
            browser.close()
        print(json.dumps({"result": "passed", "mode": "production-http-trial" if args.http_production else "development", "checks": ["教师注册与退出后重新登录", "学生手机注册后返回课堂", "学生跨浏览器登录只计一份", "学生不能访问教师页面", "我的学习", "5秒自动更新", "CSV下载", "结束课堂", "移动端无横向溢出", "无JavaScript异常"], "screenshots": str(ARTIFACTS)}, ensure_ascii=False))
    finally:
        server.terminate()
        server.wait(timeout=10)
