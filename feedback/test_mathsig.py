import json
import uuid
from unittest.mock import MagicMock, patch
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from . import test_course_features as fixtures
from .test_questions_ai_reports import CONFIG
from .mathai import remote_answer
from .models import AIConversation, AITurn, ClassroomMembership, KnowledgeBlock, Lesson


class MathSigTests(TestCase):
    setUp = fixtures.CourseFeatureTests.setUp

    def test_brand_and_simplified_course_headings(self):
        home = self.client.get(reverse('home'))
        self.assertContains(home, 'MathSig')
        self.assertNotContains(home, 'mathSXNU')
        page = self.teacher_client.get(reverse('dashboard', args=[self.lesson.code]))
        for removed in ['谁遇到了什么问题', '问题每页50份', '仅显示有点疑惑', '按板块学习与查阅资料']:
            self.assertNotContains(page, removed)
        self.assertContains(page, '课程学习空间')
        self.assertContains(page, 'class="course-columns"')
        for kind in ['knowledge', 'key', 'difficult']:
            self.assertContains(page, f'id="section-{kind}"')

    def cross_course_blocks(self):
        self.student_client.get(self.class_url)
        ClassroomMembership.objects.create(student=self.student, lesson=self.other_lesson)
        KnowledgeBlock.objects.create(lesson=self.lesson, title='方差', body='第一位老师的方差讲解')
        KnowledgeBlock.objects.create(lesson=self.other_lesson, title='方差', body='第二位老师的方差讲解')
        private = Lesson.objects.create(teacher=self.other, title='未加入的课堂')
        KnowledgeBlock.objects.create(lesson=private, title='方差', body='PRIVATE_COURSE_TEXT')
        deleted = Lesson.objects.create(teacher=self.teacher, title='回收站课堂', deleted_at=timezone.now())
        ClassroomMembership.objects.create(student=self.student, lesson=deleted)
        KnowledgeBlock.objects.create(lesson=deleted, title='方差', body='DELETED_COURSE_TEXT')

    def test_associated_classroom_does_not_limit_local_new_or_existing_chat(self):
        self.cross_course_blocks()
        result = self.student_client.post(reverse('mathai'), {
            'provider': 'local', 'lesson': self.lesson.pk, 'question': '方差是什么', 'request_id': str(uuid.uuid4()),
        })
        self.assertEqual(result.status_code, 302)
        chat = AIConversation.objects.get()
        for _ in range(2):
            turn = chat.turns.latest('pk')
            self.assertEqual(turn.status, 'complete')
            self.assertIn('第一位老师的方差讲解', turn.answer)
            self.assertIn('第二位老师的方差讲解', turn.answer)
            self.assertNotIn('PRIVATE_COURSE_TEXT', turn.answer)
            self.assertNotIn('DELETED_COURSE_TEXT', turn.answer)
            self.assertEqual(len(turn.sources), 2)
            for source in turn.sources:
                self.assertEqual(self.student_client.get(source['url']).status_code, 200)
            self.student_client.post(result.url, {'question': '方差再解释一次', 'request_id': str(uuid.uuid4())})

    @override_settings(MATHAI_PROVIDERS=CONFIG)
    def test_remote_opt_in_searches_across_courses_even_without_association(self):
        self.cross_course_blocks()
        chat = AIConversation.objects.create(user=self.student, title='跨课程', provider='deepseek', share_course=True)
        opener = MagicMock()
        opener.open.return_value.__enter__.return_value.read.return_value = json.dumps({'choices': [{'message': {'content': '参考教师讲解的回答'}}]}).encode()
        with patch('feedback.mathai.build_opener', return_value=opener):
            for lesson in [None, self.lesson]:
                chat.lesson = lesson
                answer, sources = remote_answer(chat, '方差是什么')
                payload = json.loads(opener.open.call_args.args[0].data)
                sent = json.dumps(payload, ensure_ascii=False)
                self.assertIn('第一位老师的方差讲解', sent)
                self.assertIn('第二位老师的方差讲解', sent)
                self.assertNotIn('PRIVATE_COURSE_TEXT', sent)
                self.assertNotIn('DELETED_COURSE_TEXT', sent)
                self.assertEqual(len(sources), 2)
            chat.share_course = False
            _, sources = remote_answer(chat, '方差是什么')
            self.assertFalse(sources)
            self.assertNotIn('老师的方差讲解', json.dumps(json.loads(opener.open.call_args.args[0].data), ensure_ascii=False))
