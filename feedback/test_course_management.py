import tempfile
import uuid
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from .models import AccountProfile, Lesson, Response, CourseMaterial, ResponseEvent, QuestionAttachment, AIConversation
from .mathai import available_lessons


class CourseManagementTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model()
        cls.admin = users.objects.create_superuser('开发者', password='Example!Course-4258')
        cls.teacher = users.objects.create_user('任课教师')
        cls.other = users.objects.create_user('另一教师')
        cls.student = users.objects.create_user('学生')
        cls.staff = users.objects.create_user('仅职员', is_staff=True)
        cls.super_only = users.objects.create_user('仅超级用户', is_superuser=True)
        for user in [cls.teacher, cls.other]:
            AccountProfile.objects.create(user=user, role='teacher')
        cls.lesson = Lesson.objects.create(teacher=cls.teacher, course='微积分', title='极限课堂')
        cls.other_lesson = Lesson.objects.create(teacher=cls.other, course='统计', title='方差课堂')

    def setUp(self):
        self.client.force_login(self.admin)

    def test_admin_finds_other_teacher_courses_and_opens_all_read_endpoints(self):
        page = self.client.get(reverse('developer_lessons'))
        self.assertContains(page, '极限课堂')
        self.assertContains(page, '任课教师')
        page = self.client.get(reverse('developer_lessons'), {'teacher': self.teacher.pk})
        self.assertContains(page, '极限课堂')
        self.assertNotContains(page, '方差课堂')
        page = self.client.get(reverse('developer_lessons'), {'q': '统计'})
        self.assertContains(page, '方差课堂')
        self.assertNotContains(page, '极限课堂')
        for name in ['dashboard', 'lesson_stats', 'lesson_qr', 'export_csv', 'answer_report', 'export_answers', 'student']:
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(name, args=[self.lesson.code])).status_code, 200)
        self.assertIn(self.lesson, available_lessons(self.admin))
        self.assertRedirects(self.client.get(reverse('login'), {'next': reverse('dashboard', args=[self.lesson.code])}), reverse('dashboard', args=[self.lesson.code]))

    def test_admin_can_manage_without_changing_course_ownership(self):
        self.client.post(reverse('block_create', args=[self.lesson.code]), {'kind': 'knowledge', 'title': '管理员补充', 'body': '内容', 'position': 0})
        self.assertTrue(self.lesson.blocks.filter(title='管理员补充').exists())
        self.client.post(reverse('toggle_lesson', args=[self.lesson.code]), {'action': 'close'})
        self.lesson.refresh_from_db()
        self.assertFalse(self.lesson.is_open)
        self.client.post(reverse('lesson_delete', args=[self.lesson.code]), {'confirm': 'yes'})
        self.lesson.refresh_from_db()
        self.assertIsNotNone(self.lesson.deleted_at)
        self.assertEqual(self.client.get(reverse('dashboard', args=[self.lesson.code])).status_code, 404)
        self.assertContains(self.client.get(reverse('developer_lessons'), {'archived': '1'}), self.lesson.title)
        self.client.post(reverse('lesson_restore', args=[self.lesson.code]))
        self.lesson.refresh_from_db()
        self.assertIsNone(self.lesson.deleted_at)
        self.assertEqual(self.lesson.teacher, self.teacher)
        self.assertFalse(self.lesson.is_open)

    def test_other_roles_cannot_manage_or_read_unowned_courses(self):
        for user in [self.other, self.student, self.staff, self.super_only]:
            self.client.force_login(user)
            with self.subTest(user=user):
                self.assertEqual(self.client.get(reverse('developer_lessons')).status_code, 403)
                for name in ['dashboard', 'lesson_stats', 'answer_report']:
                    self.assertIn(self.client.get(reverse(name, args=[self.lesson.code])).status_code, [403, 404])
                for name, data in [('toggle_lesson', {'action': 'close'}), ('lesson_delete', {'confirm': 'yes'}), ('block_create', {'title': '禁止'})]:
                    self.assertIn(self.client.post(reverse(name, args=[self.lesson.code]), data).status_code, [403, 404])
        self.lesson.refresh_from_db()
        self.assertTrue(self.lesson.is_open)
        self.assertIsNone(self.lesson.deleted_at)
        self.assertFalse(self.lesson.blocks.exists())

    def test_admin_downloads_files_but_other_teacher_cannot(self):
        with tempfile.TemporaryDirectory() as tmp, override_settings(MEDIA_ROOT=tmp):
            material = CourseMaterial.objects.create(lesson=self.lesson, title='课程讲义', file=SimpleUploadedFile('lesson.pdf', b'%PDF-test'), original_name='lesson.pdf', content_type='application/pdf', size=9)
            event = ResponseEvent.objects.create(lesson=self.lesson, participant=uuid.uuid4(), status='red')
            attachment = QuestionAttachment.objects.create(event=event, file=SimpleUploadedFile('question.pdf', b'%PDF-question'), original_name='question.pdf', content_type='application/pdf', size=13)
            for name, pk in [('material_file', material.pk), ('question_file', attachment.pk)]:
                self.client.force_login(self.admin)
                response = self.client.get(reverse(name, args=[pk]))
                self.assertEqual(response.status_code, 200)
                self.assertTrue(b''.join(response.streaming_content).startswith(b'%PDF'))
                self.client.force_login(self.other)
                self.assertEqual(self.client.get(reverse(name, args=[pk])).status_code, 404)
            chat = AIConversation.objects.create(user=self.teacher, title='私人对话')
            self.client.force_login(self.admin)
            self.assertEqual(self.client.get(reverse('ai_chat', args=[chat.pk])).status_code, 404)

    def test_grouped_questions_exclude_green_before_pagination_and_keep_statistics(self):
        responses = [Response(lesson=self.lesson, participant=uuid.uuid4(), status='green', note='已掌握说明') for _ in range(60)]
        responses += [Response(lesson=self.lesson, participant=uuid.uuid4(), status=status, note=text) for status, text in [('yellow', '疑惑问题'), ('red', '求助问题')]]
        Response.objects.bulk_create(responses)
        payload = self.client.get(reverse('lesson_stats', args=[self.lesson.code])).json()
        self.assertEqual(payload['total'], 62)
        self.assertEqual([row['count'] for row in payload['rows']], [60, 1, 1])
        self.assertEqual(payload['pages'], 1)
        self.assertEqual({note['status'] for note in payload['notes']}, {'yellow', 'red'})
        self.assertEqual([[n['text'] for n in group['notes']] for group in payload['question_groups']], [['疑惑问题'], ['求助问题']])
        page = self.client.get(reverse('dashboard', args=[self.lesson.code]))
        self.assertContains(page, 'id="notes-yellow"')
        self.assertContains(page, 'id="notes-red"')
        self.assertNotContains(page, '已掌握说明')
        self.assertContains(self.client.get(reverse('export_csv', args=[self.lesson.code])), '已掌握说明')
        Response.objects.filter(status__in=['yellow', 'red']).delete()
        empty = self.client.get(reverse('lesson_stats', args=[self.lesson.code]), {'feedback_page': 999}).json()
        self.assertEqual((empty['total'], empty['pages'], empty['page'], empty['notes']), (60, 1, 1, []))
