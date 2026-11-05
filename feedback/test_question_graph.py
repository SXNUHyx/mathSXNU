import json
import uuid
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from . import test_course_features as fixtures
from .models import KnowledgeBlock, Response, ResponseEvent, TeacherReply


class QuestionGraphTests(TestCase):
    setUp = fixtures.CourseFeatureTests.setUp

    def response(self, status='yellow', **extra):
        return Response.objects.create(lesson=self.lesson,participant=uuid.uuid4(),status=status,**extra)

    def graph(self, **params):
        return self.teacher_client.get(reverse('lesson_stats',args=[self.lesson.code]),params).json()['question_graph']

    def test_graph_connects_current_questions_modules_keywords_and_answer_status(self):
        block=KnowledgeBlock.objects.create(lesson=self.lesson,title='波动',body='方差与数学期望')
        response=self.response(block=block,note='方差和数学期望是什么',user=self.student,real_name='张同学',student_number='001')
        event=ResponseEvent.objects.create(lesson=self.lesson,participant=response.participant,user=self.student,status='yellow',note=response.note)
        self.response('red',note='',real_name='等待帮助')
        self.response('green',note='已听懂，不应在图谱内')
        graph=self.graph()
        self.assertEqual(graph['total'],2)
        question=next(q for q in graph['questions'] if q['id']==response.pk)
        self.assertEqual(question['module_id'],f'block-{block.pk}')
        self.assertIn('方差',question['keywords'])
        self.assertIn('数学期望',question['keywords'])
        self.assertFalse(question['answered'])
        self.assertEqual(question['number'],'001')
        self.assertEqual(self.teacher_client.get(question['reply_url']).status_code,200)
        blank=next(q for q in graph['questions'] if q['status']=='red')
        self.assertEqual((blank['module'],blank['keywords'],blank['reply_url']),('未关联模块',[],''))
        TeacherReply.objects.create(response=response,teacher=self.teacher,question_event=event,question_text=response.note,message='解释')
        self.assertTrue(next(q for q in self.graph()['questions'] if q['id']==response.pk)['answered'])
        ResponseEvent.objects.create(lesson=self.lesson,participant=response.participant,status='yellow',note='再次追问')
        self.assertFalse(next(q for q in self.graph()['questions'] if q['id']==response.pk)['answered'])

    def test_graph_is_lesson_scoped_and_does_not_expose_private_ai_or_other_courses(self):
        Response.objects.create(lesson=self.other_lesson,participant=uuid.uuid4(),status='red',note='PRIVATE_OTHER_LESSON')
        self.response(note='本课方差问题')
        self.assertNotIn('PRIVATE_OTHER_LESSON',json.dumps(self.graph()))
        url=reverse('lesson_stats',args=[self.lesson.code])
        self.assertEqual(self.student_client.get(url).status_code,403)
        self.assertEqual(self.other_client.get(url).status_code,404)
        self.client.force_login(get_user_model().objects.create_superuser('图谱管理员',password='Graph!Example-8543'))
        self.assertEqual(self.client.get(url).status_code,200)

    def test_graph_is_independent_of_pagination_and_discloses_bounded_sample(self):
        for _ in range(52):
            self.response(note='方差')
        self.assertEqual(self.graph(),self.graph(feedback_page=2))
        with patch('feedback.question_graph.GRAPH_LIMIT',3):
            graph=self.graph()
        self.assertEqual((graph['total'],graph['limit'],len(graph['questions'])),(52,3,3))

    def test_empty_and_unsafe_text_are_handled_without_html_interpolation(self):
        self.assertEqual(self.graph()['questions'],[])
        self.response(note='</script><script>alert(1)</script>',real_name='<img src=x onerror=alert(2)>')
        page=self.teacher_client.get(reverse('dashboard',args=[self.lesson.code]))
        self.assertContains(page,'id="question-graph"')
        self.assertNotContains(page,'</script><script>alert(1)</script>')
        self.assertNotContains(page,'<img src=x onerror=alert(2)>')
