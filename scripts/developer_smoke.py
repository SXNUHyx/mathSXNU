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
from feedback.models import AccountProfile, Lesson, Response, ResponseEvent, CourseMaterial, KnowledgeBlock
from django.core.files.base import ContentFile
import uuid
password=json.loads(sys.stdin.readline())
admin=get_user_model().objects.create_superuser('演示管理员',password=password)
t=get_user_model().objects.create_user('演示教师',password=password)
AccountProfile.objects.create(user=t,role='teacher',real_name='演示教师')
for i in range(4):
    own_lesson=Lesson.objects.create(teacher=admin,course='管理员课程',title=f'布局课堂{i}')
    if i==0:
        KnowledgeBlock.objects.create(lesson=own_lesson,title='方差',body='跨教师另一课堂的方差说明')
lesson=Lesson.objects.create(teacher=t,course='微积分',title='教师课程检查')
for kind in ['knowledge','key','difficult']:
    KnowledgeBlock.objects.create(lesson=lesson,kind=kind,title='方差'+kind,body='本课堂的方差说明')
Response.objects.create(lesson=lesson,participant=uuid.uuid4(),status='yellow',real_name='待答学生',note='尚未回复的问题')
for status,name in [('green','已经听懂的学生'),('yellow','有疑惑的学生'),('red','需要帮助的学生')]:
    response=Response.objects.create(lesson=lesson,participant=uuid.uuid4(),user=t if status=='yellow' else None,status=status,real_name=name,note='方差与数学期望：'+name+'的问题',block=lesson.blocks.filter(kind='knowledge').first() if status=='yellow' else None)
    ResponseEvent.objects.create(lesson=lesson,participant=response.participant,user=response.user,status=status,note=response.note)
material=CourseMaterial(lesson=lesson,title='教师讲义',original_name='lesson.pdf',content_type='application/pdf',size=9)
material.file.save('lesson.pdf',ContentFile(b'%PDF-test'),save=True)
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
            # Cross-teacher course management and responsive four-column cards.
            admin.set_viewport_size({'width':1440,'height':1000})
            admin.goto(base+'/teacher/')
            cards=admin.locator('.teacher-lesson-grid .lesson-card')
            assert cards.count()==4
            boxes=[cards.nth(i).bounding_box() for i in range(4)]
            assert max(b['y'] for b in boxes)-min(b['y'] for b in boxes)<1
            admin.set_viewport_size({'width':390,'height':844})
            assert admin.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            assert cards.nth(1).bounding_box()['y']>cards.nth(0).bounding_box()['y']
            admin.set_viewport_size({'width':1440,'height':1000})
            admin.get_by_role('link',name='管理全站教师课程',exact=False).click()
            admin.get_by_label('搜索课程、教师或课堂码').fill('演示教师')
            admin.get_by_role('button',name='查询课程',exact=True).click()
            assert admin.locator('.lesson-card').count()==1
            admin.get_by_role('link',name='查看课程与资料',exact=False).click()
            assert '演示教师' in admin.locator('.notice').inner_text()
            assert 'MathSig' in admin.locator('.brand').inner_text()
            assert 'mathSXNU' not in admin.locator('body').inner_text()
            for removed in ['谁遇到了什么问题','问题每页50份','仅显示有点疑惑','按板块学习与查阅资料']:
                assert removed not in admin.locator('body').inner_text()
            sections=admin.locator('.course-columns > section')
            assert sections.count()==3
            section_boxes=[sections.nth(i).bounding_box() for i in range(3)]
            assert max(b['y'] for b in section_boxes)-min(b['y'] for b in section_boxes)<1
            assert admin.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            admin.screenshot(path=str(ARTIFACTS/'mathsig-course-columns.png'),full_page=True)
            assert '有疑惑的学生' in admin.locator('#notes-yellow').inner_text()
            assert '需要帮助的学生' in admin.locator('#notes-red').inner_text()
            assert '已经听懂的学生' not in admin.locator('#notes').inner_text()
            assert admin.locator('#count-green').inner_text()=='1'
            with admin.expect_download() as course_download:
                admin.get_by_role('link',name='教师讲义',exact=False).click()
            assert Path(course_download.value.path()).read_bytes()==b'%PDF-test'
            assert admin.locator('#question-people-yellow').inner_text()=='2'
            assert admin.locator('#question-total-yellow').inner_text()=='2'
            assert admin.locator('#question-resolved-yellow').inner_text()=='0'
            admin.get_by_role('button',name='关键词：方差',exact=False).click()
            assert admin.locator('#graph-questions .graph-question').count()==2
            assert '关键词：方差' in admin.locator('#graph-detail-title').inner_text()
            admin.get_by_label('反馈类型',exact=True).select_option('yellow')
            admin.get_by_role('button',name='关键词：方差',exact=False).focus()
            admin.keyboard.press('Enter')
            assert admin.locator('#graph-questions .graph-question').count()==1
            admin.get_by_role('button',name='查看全部关联',exact=True).click()
            assert admin.locator('#graph-questions .graph-question').count()==3
            admin.locator('#question-graph').screenshot(path=str(ARTIFACTS/'problem-graph-desktop.png'))

            # Replying moves a question behind pending questions, including on a polling dashboard.
            assert '有疑惑的学生' in admin.locator('#notes-yellow .feedback-note').first.inner_text()
            watcher=context.new_page();watcher.goto(admin.url)
            watcher.get_by_label('答疑状态',exact=True).select_option('pending')
            assert watcher.locator('#graph-questions .graph-question').count()==3
            admin.locator('#notes-yellow .feedback-note').filter(has_text='有疑惑的学生').get_by_role('link',name='回复这位学生',exact=False).click()
            admin.get_by_label('给学生的解释',exact=True).fill('已回复当前问题，请对照讲解继续学习。')
            admin.get_by_role('button',name='发送解释',exact=False).click()
            assert '待答学生' in admin.locator('#notes-yellow .feedback-note').first.inner_text()
            assert '有疑惑的学生' in admin.locator('#notes-yellow .feedback-note').last.inner_text()
            watcher.bring_to_front()
            watcher.wait_for_function("document.querySelector('#notes-yellow .feedback-note').textContent.includes('待答学生')",timeout=12000)
            assert '有疑惑的学生' in watcher.locator('#notes-yellow .feedback-note').last.inner_text()
            assert watcher.locator('#question-resolved-yellow').inner_text()=='1'
            assert watcher.locator('#question-pending-yellow').inner_text()=='1'
            assert watcher.locator('#graph-questions .graph-question').count()==2
            followup="from feedback.models import Response,ResponseEvent; r=Response.objects.get(real_name='有疑惑的学生'); ResponseEvent.objects.create(lesson=r.lesson,participant=r.participant,user=r.user,status='yellow',note='再次追问'); r.note='再次追问'; r.save()"
            subprocess.run([PYTHON,'manage.py','shell','-c',followup],cwd=ROOT,env=env,check=True,stdout=subprocess.DEVNULL)
            watcher.wait_for_function("document.querySelector('#question-total-yellow').textContent==='3' && document.querySelector('#question-pending-yellow').textContent==='2'",timeout=12000)
            assert watcher.locator('#question-people-yellow').inner_text()=='2'
            assert watcher.locator('#question-resolved-yellow').inner_text()=='1'
            watcher.close();admin.bring_to_front()
            # A changed signal must move between groups on the next poll.
            update="from feedback.models import Response; Response.objects.filter(real_name='需要帮助的学生').update(status='yellow')"
            subprocess.run([PYTHON,'manage.py','shell','-c',update],cwd=ROOT,env=env,check=True,stdout=subprocess.DEVNULL)
            admin.wait_for_function("document.querySelector('#notes-yellow').textContent.includes('需要帮助的学生') && !document.querySelector('#notes-red').textContent.includes('需要帮助的学生')",timeout=12000)
            assert admin.locator('#question-count-yellow').inner_text()=='3'
            assert admin.locator('#question-count-red').inner_text()=='0'
            admin.set_viewport_size({'width':390,'height':844})
            assert admin.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            assert admin.locator('#notes-red').bounding_box()['y']>admin.locator('#notes-yellow').bounding_box()['y']
            assert sections.nth(1).bounding_box()['y']>sections.nth(0).bounding_box()['y']
            admin.locator('#question-graph').screenshot(path=str(ARTIFACTS/'problem-graph-mobile.png'))
            admin.get_by_role('link',name='本课堂MathAI',exact=True).click()
            assert admin.locator('#id_lesson').input_value()
            admin.get_by_label('您的问题',exact=True).fill('方差是什么意思')
            admin.get_by_role('button',name='发送问题',exact=False).click()
            admin.locator('#ai-turns').get_by_text('跨教师另一课堂的方差说明',exact=False).wait_for()
            assert admin.locator('#ai-turns .notification-link').count()>0
            assert not errors,errors
            browser.close()
        print(json.dumps({'result':'passed','checks':['交互问题图谱与筛选及答疑后轮询更新','提问人数次数与已解决实时统计及追问计数','未回答优先与回复后自动排后','MathSig品牌与简洁界面','课程学习空间桌面三列与手机单列','MathAI关联课堂时跨教师课程检索','管理员跨教师课程和资料访问','桌面四列和手机单列课堂','疑惑与求助独立分组及自动刷新','管理员登录跳转','中文账号创建与资料修改','JSON搜索与CSRF写入','CSV导出','归档取消与确认','恢复后显式启用','学生拒绝管理访问','重置后原会话失效与新密码登录','可查操作日志','手机布局','无外部请求'],'screenshots':str(ARTIFACTS)},ensure_ascii=False))
    finally:
        server.terminate();server.wait(timeout=10)
