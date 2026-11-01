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
            teacher.get_by_label("用户名", exact=False).fill("王老师")
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
            teacher.get_by_label("用户名", exact=False).fill("王老师")
            teacher.get_by_label("密码", exact=True).fill(password)
            teacher.get_by_role("button", name="登录", exact=False).click()
            teacher.get_by_role("heading", name="每一个信号，都值得看见。", exact=True).wait_for()
            teacher.get_by_role("link", name="创建我的第一个课堂").click()
            teacher.get_by_label("课程名称").fill("统计学 · 演示课程")
            teacher.get_by_label("本次课堂 / 知识点").fill("均值与方差")
            teacher.get_by_label("预计参与人数").fill("40")
            teacher.get_by_role("button", name="创建并获取课堂码").click()
            teacher.wait_for_selector("#dashboard")
            student_url = teacher.locator("#student-link").input_value()
            dashboard_url = teacher.url
            for kind, title in [("knowledge", "总体均值"), ("key", "重点公式"), ("difficult", "方差的含义")]:
                teacher.get_by_role("link", name="＋ 添加模块", exact=True).click()
                teacher.get_by_label("模块类型").select_option(kind)
                teacher.get_by_label("模块标题").fill(title)
                teacher.get_by_label("内容（支持LaTeX）", exact=True).fill(r"期望定义：\[E(X)=\sum_i x_i p_i\]")
                teacher.locator('.math-preview .katex').first.wait_for()
                teacher.get_by_role("button", name="保存模块", exact=True).click()
            from PIL import Image
            image_path = Path(tmp) / "知识点图片.png"
            Image.new("RGB", (160, 100), "#dbeede").save(image_path)
            pdf_path = Path(tmp) / "课程资料.pdf"
            teacher.pdf(path=str(pdf_path))
            for title, path in [("均值示意图", image_path), ("课程讲义PDF", pdf_path)]:
                teacher.get_by_role("link", name="上传图片 / 资料", exact=True).click()
                teacher.get_by_label("资料或图片名称").fill(title)
                if path.suffix == ".png":
                    teacher.get_by_label("关联模块（选填）", exact=True).select_option(label="知识点 · 总体均值")
                teacher.get_by_label("选择文件", exact=True).set_input_files(str(path))
                teacher.get_by_role("button", name="上传并发布", exact=True).click()
            mobile_context = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
            student = mobile_context.new_page()
            student.on("pageerror", lambda e: errors.append(str(e)))
            student.goto(student_url)
            # Exercise the generic navbar route that used to lose the classroom next URL.
            student.get_by_role("navigation").get_by_role("link", name="注册", exact=True).click()
            student.get_by_role("link", name="我是学生，参与课堂", exact=False).click()
            student.screenshot(path=str(ARTIFACTS / "student-register-mobile.png"), full_page=True)
            student.get_by_label("用户名", exact=False).fill("张小明")
            student.get_by_label("密码", exact=True).fill(password)
            student.get_by_label("密码确认", exact=True).fill(password)
            student.get_by_role("button", name="注册学生账号").click()
            assert student.url == student_url
            student.get_by_label('姓名', exact=True).fill('张小明')
            student.get_by_label('学号', exact=True).fill('0012026001')
            student.get_by_role("radio", name="需要帮助").check()
            student.get_by_label("想让老师多讲一点什么").fill("方差为什么不能直接用均值代替？")
            student.get_by_role("button", name="把信号送给老师").click()
            student.get_by_role("status").filter(has_text="反馈已送达老师").wait_for()
            student.screenshot(path=str(ARTIFACTS / "student-mobile.png"), full_page=True)
            teacher.wait_for_function("document.querySelector('#count-red').textContent === '1'", timeout=10000)
            teacher.wait_for_timeout(500)  # Let the chart's short CSS transition settle for the screenshot.
            assert teacher.locator("#total").inner_text() == "1"
            assert "张小明" in teacher.locator('#notes').inner_text()
            assert "0012026001" in teacher.locator('#notes').inner_text()
            teacher.get_by_role('link', name='回复这位学生', exact=False).first.click()
            teacher.get_by_label('给学生的解释', exact=True).fill(r"方差刻画波动：\(\operatorname{Var}(X)=E[X^2]-E[X]^2\)。请先计算偏差。")
            teacher.get_by_role('button', name='发送解释', exact=False).click()
            student.wait_for_function("document.querySelector('#reply-list').textContent.includes('方差刻画波动')", timeout=12000)
            student.locator('#reply-list .katex').first.wait_for()
            student.locator('#teacher-replies').screenshot(path=str(ARTIFACTS / 'student-replies.png'))
            student.get_by_role('button', name='标记以上回复为已读', exact=True).click()
            student.wait_for_function("document.querySelector('#reply-list').textContent.includes('已读')", timeout=10000)
            image = student.get_by_alt_text('均值示意图', exact=True).first
            image.scroll_into_view_if_needed()
            image.wait_for()
            assert image.evaluate('(img) => img.complete && img.naturalWidth > 0')
            with student.expect_download() as file_download:
                student.get_by_role('link', name='课程讲义PDF', exact=False).first.click()
            assert file_download.value.suggested_filename.endswith('.pdf')
            # A new browser logged into the same student account sees and updates one response.
            second_context = browser.new_context(viewport={"width": 1366, "height": 900})
            second = second_context.new_page()
            second.goto(student_url)
            second.get_by_label("用户名", exact=False).fill("张小明")
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
            assert "方差为什么不能直接用均值代替" in teacher.locator("#notes").inner_text()
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
            assert student.locator('#feedback-form').count() == 0
            # Mobile dashboard and homepage must not overflow horizontally.
            teacher.set_viewport_size({"width": 390, "height": 844})
            teacher.screenshot(path=str(ARTIFACTS / "teacher-mobile.png"), full_page=True)
            assert teacher.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            teacher.get_by_role('link', name='删除课堂', exact=True).click()
            teacher.get_by_role('button', name='确认删除课堂', exact=True).click()
            assert teacher.locator('.lesson-card').count() == 0
            result = student.goto(student_url)
            assert result.status == 404
            teacher.get_by_role('link', name='课堂回收站', exact=False).click()
            teacher.get_by_role('button', name='恢复课堂', exact=True).click()
            assert teacher.locator('.knowledge-block').count() == 3
            assert '方差刻画波动' in teacher.locator('#notes').inner_text()
            student.goto(base)
            student.screenshot(path=str(ARTIFACTS / "home-mobile.png"), full_page=True)
            assert student.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            assert not errors, errors
            browser.close()
        print(json.dumps({"result": "passed", "mode": "production-http-trial" if args.http_production else "development", "checks": ["师生中文用户名注册与登录", "知识点重点难点模块", "LaTeX编辑预览及学生渲染", "图片上传与受保护读取", "PDF上传下载", "姓名学号反馈", "教师回复自动到达学生端", "回复已读", "学生跨设备去重", "课堂删除与恢复", "权限隔离", "CSV下载", "移动端适配"], "screenshots": str(ARTIFACTS)}, ensure_ascii=False))
    finally:
        server.terminate()
        server.wait(timeout=10)
