import io
import re
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from docx import Document
from docx.shared import Inches, Pt
from docx.oxml.ns import qn
from PIL import Image
from .roles import teacher_required
from .course_views import owned
from .insights import keyword_insights, student_sort_key


def report_context(lesson):
    responses = list(lesson.responses.select_related('user', 'block').prefetch_related('replies__teacher'))
    records = list(lesson.events.select_related('block').prefetch_related('attachments').order_by('created_at','pk'))
    groups = []
    for response in sorted(responses, key=lambda r:(student_sort_key(r.student_number), r.real_name, r.pk)):
        events = [event for event in records if event.participant == response.participant]
        timeline = [{'time': e.created_at, 'kind':'question', 'item':e} for e in events]
        timeline += [{'time': r.created_at, 'kind':'reply', 'item':r} for r in response.replies.all()]
        timeline.sort(key=lambda e:(e['time'], e['kind']=='reply',e['item'].pk))
        groups.append({'response':response,'timeline':timeline})
    return {'lesson':lesson,'groups':groups,'insights':keyword_insights(records),'generated':timezone.localtime()}


@teacher_required
@never_cache
def answer_report(request, code):
    return render(request, 'answer_report.html', report_context(owned(request,code)))


def safe_text(value):
    return re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]', '', str(value))


@teacher_required
@never_cache
def export_answers(request, code):
    context = report_context(owned(request,code))
    document = Document()
    style = document.styles['Normal']
    style.font.name = 'Microsoft YaHei'
    style.element.rPr.rFonts.set(qn('w:eastAsia'), 'Microsoft YaHei')
    style.font.size = Pt(10.5)
    def p(text, heading=None):
        return document.add_heading(safe_text(text),level=heading) if heading else document.add_paragraph(safe_text(text))
    lesson = context['lesson']
    p('课堂提问与教师答疑归档',1)
    p(f'{lesson.course} / {lesson.title} · 课堂码 {code}')
    p('生成时间（北京时间）：'+context['generated'].strftime('%Y-%m-%d %H:%M:%S'))
    p('按当前学号自然顺序排列（2在10之前，开头的0保留）；未填写学号的历史记录排在最后。身份由学生自填。包含本课堂全部历史提问、附件名称和教师解释，不包含私人AI会话。')
    p('公式以LaTeX原文保留；如需公式排版与图片，请使用网页“打印 / 保存PDF”。附件文件本身不打包进Word，图片按导出体积限制嵌入。')
    p('整个答疑过程的历史疑问关键词',2)
    p(f"统计历史黄/红反馈，共 {context['insights']['questions']} 次记录、疑问学生 {context['insights']['students']} 人；每个词每人只计一次，不分析附件内容。")
    for term in context['insights']['terms']:
        p(f"{term['term']}：{term['count']}人（疑问学生中的{term['percent']}%）")
    image_budget = 30 * 1024 * 1024
    for group in context['groups']:
        record = group['response']
        p(f"学号 {record.student_number or '未填写'} · {record.real_name or (record.user.username if record.user_id else '历史不记名')}",2)
        p('当前状态：'+record.get_status_display())
        if not group['timeline']:
            p('当前记录：'+record.note)
        for entry in group['timeline']:
            item = entry['item']
            stamp = timezone.localtime(entry['time']).strftime('%Y-%m-%d %H:%M:%S')
            if entry['kind'] == 'reply':
                p('教师解释 · '+stamp,3)
                p('针对问题：'+item.question_text)
                p(item.message)
                p('学生已读' if item.student_read_at else '学生未读')
            else:
                p('学生提问 · '+stamp,3)
                p(f'当时姓名：{item.real_name or "未填写"} · 当时学号：{item.student_number or "未填写"}')
                if item.block_title:
                    p('相关模块：'+item.block_title)
                p(item.note or '仅提交状态或附件')
                for attachment in item.attachments.all():
                    p('附件：'+attachment.original_name)
                    if attachment.is_image and image_budget > 0:
                        try:
                            with attachment.file.open('rb') as source, Image.open(source) as image:
                                image.thumbnail((1200,1200))
                                output = io.BytesIO()
                                image.convert('RGB').save(output,format='JPEG',quality=80)
                            if len(output.getvalue()) <= image_budget:
                                document.add_picture(io.BytesIO(output.getvalue()),width=Inches(4.8))
                                image_budget -= len(output.getvalue())
                        except (OSError, ValueError):
                            p('图片暂不可用，请在平台查看原附件。')
    output = io.BytesIO()
    document.save(output)
    response = HttpResponse(output.getvalue(),content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
    response['Content-Disposition'] = f'attachment; filename="classroom-{code}-answers.docx"'
    return response
