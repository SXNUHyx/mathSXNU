"""Real-browser developer console checks using only a disposable SQLite database.

Run after collectstatic, with a Python interpreter that has Playwright installed:
    python scripts/developer_smoke.py
Never connects to a production server. All names and credentials are test data.
"""
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import tempfile
import time
from urllib.request import urlopen
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parent.parent
PYTHON=str(ROOT/'.venv/bin/python')
ARTIFACTS=ROOT/'.local/screenshots'
ARTIFACTS.mkdir(parents=True,exist_ok=True)
password=secrets.token_urlsafe(24)
new_password=secrets.token_urlsafe(24)

with tempfile.TemporaryDirectory(prefix='mathsxnu-developer-') as tmp:
    env={**os.environ,'DJANGO_DEBUG':'1','DJANGO_DB_PATH':str(Path(tmp)/'db.sqlite3'),
         'DJANGO_MEDIA_ROOT':str(Path(tmp)/'media'),'DEEPSEEK_API_KEY':'','DOUBAO_API_KEY':'','KIMI_API_KEY':''}
    subprocess.run([PYTHON,'manage.py','migrate','--noinput'],cwd=ROOT,env=env,check=True,stdout=subprocess.DEVNULL)
    # Pass test credentials through stdin, not shell arguments or logs.
    seed="""import json,sys
from django.contrib.auth import get_user_model
from feedback.models import AccountProfile
password=json.loads(sys.stdin.readline())
get_user_model().objects.create_superuser('演示管理员',password=password)
t=get_user_model().objects.create_user('演示教师',password=password)
AccountProfile.objects.create(user=t,role='teacher',real_name='演示教师')
"""
    subprocess.run([PYTHON,'manage.py','shell','-c',seed],input=json.dumps(password)+'\n',cwd=ROOT,env=env,text=True,check=True,stdout=subprocess.DEVNULL)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    base=f'http://127.0.0.1:{port}'
    env['DJANGO_PUBLIC_ORIGIN']=base
    server=subprocess.Popen([str(ROOT/'.venv/bin/gunicorn'),'mathsxnu.wsgi:application','--bind',f'127.0.0.1:{port}','--workers','1','--threads','4'],cwd=ROOT,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        for _ in range(50):
            try:
                urlopen(base+'/health/',timeout=1).close();break
            except OSError:
                if server.poll() is not None: raise RuntimeError('Test server exited')
                time.sleep(.1)
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH','/usr/bin/chromium'),args=['--no-sandbox'])
            context=browser.new_context(viewport={'width':1440,'height':1000})
            errors=[];external=[]
            context.on('request',lambda req: external.append(req.url) if req.url.startswith(('http:','https:')) and not req.url.startswith(base+'/') else None)
            admin=context.new_page();admin.on('pageerror',lambda error: errors.append(str(error)))
            admin.on('dialog',lambda dialog: dialog.accept())
            admin.goto(base+'/developer/')
            admin.get_by_label('用户名',exact=False).fill('演示管理员')
            admin.get_by_label('密码',exact=True).fill(password)
            admin.get_by_role('button',name='登录',exact=False).click()
            admin.get_by_role('heading',name='全站用户管理',exact=True).wait_for()
            assert admin.locator('#manager-count-total').inner_text()=='2'
            admin.get_by_role('link',name='＋ 创建账号',exact=True).click()
            admin.get_by_label('用户名',exact=False).fill('后台测试学生')
            admin.get_by_label('初始密码',exact=True).fill(password)
            admin.get_by_label('确认初始密码',exact=True).fill(password)
            admin.get_by_label('姓名（账号资料）',exact=True).fill('李同学')
            admin.get_by_label('学号（账号资料）',exact=True).fill('0012026001')
            admin.get_by_label('账号角色',exact=True).select_option('student')
            admin.get_by_role('button',name='创建账号',exact=True).click()
            admin.get_by_role('heading',name='管理：后台测试学生',exact=True).wait_for()
            detail=admin.url
            admin.get_by_label('姓名（账号资料）',exact=True).fill('李同学已核对')
            admin.get_by_role('button',name='保存账号资料',exact=True).click()
            admin.get_by_role('status').filter(has_text='账号资料已更新').wait_for()
            admin.screenshot(path=str(ARTIFACTS/'developer-user-detail.png'),full_page=True)
            admin.goto(base+'/developer/')
            admin.get_by_label('账号 / 姓名 / 学号 / 邮箱',exact=True).fill('0012026001')
            with admin.expect_response(lambda r:'/developer/api/users/?' in r.url and r.request.method=='GET') as query:
                admin.get_by_role('button',name='搜索用户',exact=True).click()
            assert query.value.status==200
            admin.wait_for_function("document.querySelector('#manager-rows').textContent.includes('李同学已核对') && !document.querySelector('#manager-error').textContent")
            assert admin.locator('#manager-rows tr').count()==1
            with admin.expect_download() as download:
                admin.get_by_role('link',name='导出筛选用户CSV',exact=True).click()
            csv_path=Path(tmp)/'users.csv';download.value.save_as(str(csv_path))
            csv_text=csv_path.read_text(encoding='utf-8-sig')
            assert '0012026001' in csv_text and '后台测试学生' in csv_text and password not in csv_text
            admin.screenshot(path=str(ARTIFACTS/'developer-users.png'),full_page=True)
            admin.set_viewport_size({'width':390,'height':844})
            assert admin.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            admin.screenshot(path=str(ARTIFACTS/'developer-mobile.png'),full_page=True)
            admin.goto(detail)
            admin.get_by_role('link',name='归档账号',exact=True).click()
            admin.get_by_role('link',name='取消',exact=True).click()
            assert admin.get_by_role('link',name='归档账号',exact=True).count()==1
            admin.get_by_role('link',name='归档账号',exact=True).click()
            admin.get_by_role('button',name='确认归档账号',exact=True).click()
            admin.get_by_role('link',name='恢复账号',exact=True).wait_for()
            admin.get_by_role('link',name='恢复账号',exact=True).click()
            admin.get_by_role('button',name='确认恢复账号',exact=True).click()
            admin.get_by_role('link',name='启用账号',exact=True).wait_for()
            admin.get_by_role('link',name='启用账号',exact=True).click()
            admin.get_by_role('button',name='确认启用账号',exact=True).click()
            student_context=browser.new_context(viewport={'width':390,'height':844},is_mobile=True,has_touch=True)
            student=student_context.new_page()
            student.goto(base+'/accounts/login/')
            student.get_by_label('用户名',exact=False).fill('后台测试学生')
            student.get_by_label('密码',exact=True).fill(password)
            student.get_by_role('button',name='登录',exact=False).click()
            student.get_by_role('heading',name='我的学习',exact=True).wait_for()
            assert student.goto(base+'/developer/').status==403
            admin.get_by_role('link',name='重置密码',exact=True).click()
            admin.get_by_label('新密码',exact=True).fill(new_password)
            admin.get_by_label('确认新密码',exact=True).fill(new_password)
            admin.get_by_role('button',name='确认重置密码',exact=True).click()
            student.goto(base+'/student/')
            student.get_by_label('用户名',exact=False).wait_for()
            student.get_by_label('用户名',exact=False).fill('后台测试学生')
            student.get_by_label('密码',exact=True).fill(new_password)
            student.get_by_role('button',name='登录',exact=False).click()
            student.get_by_role('heading',name='我的学习',exact=True).wait_for()
            admin.goto(base+'/developer/')
            result=admin.evaluate("""async () => {
                const token=document.querySelector('[name=csrfmiddlewaretoken]').value;
                const r=await fetch('/developer/api/users/',{method:'POST',headers:{'Content-Type':'application/json','X-CSRFToken':token},body:JSON.stringify({username:'接口创建测试',role:'student',password1:'Example!Study-7285-token',password2:'Example!Study-7285-token'})});
                return {status:r.status,data:await r.json()};
            }""")
            assert result['status']==201,result
            admin.goto(base+'/developer/audit/')
            admin.get_by_role('heading',name='开发者操作日志',exact=True).wait_for()
            text=admin.locator('#main').inner_text()
            assert all(label in text for label in ['创建账号','归档账号','恢复账号','启用账号','重置密码'])
            assert password not in text and new_password not in text
            admin.screenshot(path=str(ARTIFACTS/'developer-audit.png'),full_page=True)
            assert admin.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            assert not errors,errors
            assert not external,external
            browser.close()
        print(json.dumps({'result':'passed','checks':['管理员登录跳转','中文账号创建与资料修改','JSON搜索与CSRF写入','CSV导出','归档取消与确认','恢复后显式启用','学生拒绝管理访问','重置后原会话失效与新密码登录','可查操作日志','手机布局','无外部请求'],'screenshots':str(ARTIFACTS)},ensure_ascii=False))
    finally:
        server.terminate();server.wait(timeout=10)
