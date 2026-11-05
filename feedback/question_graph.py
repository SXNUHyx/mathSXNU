"""Lesson-scoped graph inputs from current feedback, with no inferred causal edges."""
from django.urls import reverse
from .insights import terms

GRAPH_LIMIT = 300
GRAPH_STOP = {'回复', '尚未', '帮助', '疑惑', '追问', '听懂', '补充', '说明'}


def question_graph(lesson, responses):
    questions = [r for r in responses if r.status in ('yellow', 'red')]
    records = []
    for r in questions[:GRAPH_LIMIT]:
        records.append({
            'id': r.pk, 'status': r.status, 'answered': r.answered_at is not None,
            'name': r.real_name or (r.user.username if r.user_id else '历史不记名'),
            'number': r.student_number or '未填写', 'text': r.note[:600] + ('…' if len(r.note) > 600 else ''),
            'module_id': f'block-{r.block_id}' if r.block_id else 'unassigned',
            'module': str(r.block) if r.block_id else '未关联模块',
            'keywords': sorted(terms(r.note) - GRAPH_STOP),
            'reply_url': reverse('reply_create', args=[lesson.code, r.pk]) if r.user_id else '',
        })
    return {'title': lesson.title, 'total': len(questions), 'limit': GRAPH_LIMIT, 'questions': records}
