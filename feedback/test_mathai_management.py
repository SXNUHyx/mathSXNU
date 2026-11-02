import uuid
from datetime import timedelta
from unittest.mock import patch
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from . import test_course_features as fixtures
from . import test_questions_ai_reports as ai_fixtures
from .models import Lesson, AIConversation, AITurn, AIUsageDay


class MathAIManagementTests(TestCase):
    setUp = fixtures.CourseFeatureTests.setUp
    ask = ai_fixtures.MathAITests.ask

    def chat(self, user=None, **fields):
        conversation = AIConversation.objects.create(user=user or self.student, title='需要删除的私人会话', **fields)
        AITurn.objects.create(conversation=conversation, request_id=uuid.uuid4(), question='私人问题', answer='解释', status='complete')
        return conversation

    def delete_url(self, conversation):
        return reverse('ai_delete',args=[conversation.pk])

    def test_students_choose_actual_joined_classroom_names(self):
        self.student_client.get(self.class_url)
        page = self.student_client.get(reverse('mathai'))
        self.assertContains(page, str(self.lesson))
        self.assertNotContains(page, 'Lesson object')
        self.assertNotContains(page, self.other_lesson.title)
        self.assertEqual(list(page.context['form'].fields['lesson'].queryset), [self.lesson])
        page = self.peer_client.get(reverse('mathai'))
        self.assertFalse(page.context['form'].fields['lesson'].queryset.exists())

    def test_teacher_options_only_include_own_lessons_and_codes_disambiguate_names(self):
        duplicate = Lesson.objects.create(teacher=self.teacher,course=self.lesson.course,title=self.lesson.title)
        page = self.teacher_client.get(reverse('mathai'))
        self.assertEqual(set(page.context['form'].fields['lesson'].queryset), {self.lesson,duplicate})
        self.assertContains(page,str(self.lesson));self.assertContains(page,str(duplicate))
        self.assertNotEqual(str(duplicate),str(self.lesson))
        self.assertNotContains(page,self.other_lesson.title)
        self.assertEqual(self.ask(client=self.teacher_client,lesson=self.other_lesson.pk).status_code,200)
        self.assertFalse(AIConversation.objects.exists())

    def test_classroom_entry_prefills_and_saves_the_selected_lesson(self):
        self.student_client.get(self.class_url)
        page = self.student_client.get(reverse('mathai')+'?lesson='+self.lesson.code)
        self.assertEqual(page.context['form']['lesson'].value(),self.lesson.pk)
        result = self.ask(lesson=self.lesson.pk)
        conversation = AIConversation.objects.get()
        self.assertEqual(conversation.lesson_id,self.lesson.pk)
        self.assertContains(self.student_client.get(result.url),str(self.lesson))

    def test_name_is_mathai_in_selector_status_and_existing_chat(self):
        conversation = self.chat()
        page = self.student_client.get(reverse('mathai'))
        self.assertEqual(page.context['form'].fields['provider'].choices[0],('local','MathAI'))
        self.assertNotContains(page,'本地 MathAI · 课程检索（非大模型）')
        page = self.student_client.get(reverse('ai_chat',args=[conversation.pk]))
        self.assertEqual(page.context['provider_label'],'MathAI')
        self.assertNotContains(page,'非大模型')
        conversation.refresh_from_db();self.assertEqual(conversation.provider,'local')

    def test_confirmation_get_and_cancel_preserve_contents_post_requires_confirmation(self):
        conversation = self.chat()
        page = self.student_client.get(self.delete_url(conversation))
        self.assertContains(page,'确认删除会话')
        self.assertContains(page,'取消，保留会话')
        self.student_client.get(reverse('mathai'))
        self.assertEqual(self.student_client.post(self.delete_url(conversation),{}).status_code,400)
        self.assertEqual(AITurn.objects.count(),1)
        self.assertEqual(AIConversation.objects.count(),1)

    def test_delete_removes_only_owned_chat_and_turns_and_old_urls_stop_working(self):
        mine,peer,another = self.chat(),self.chat(user=self.peer),self.chat()
        result = self.student_client.post(self.delete_url(mine),{'confirm':'yes'})
        self.assertRedirects(result,reverse('mathai'))
        self.assertFalse(AIConversation.objects.filter(pk=mine.pk).exists())
        self.assertFalse(AITurn.objects.filter(conversation_id=mine.pk).exists())
        self.assertEqual(set(AIConversation.objects.values_list('pk',flat=True)),{peer.pk,another.pk})
        self.assertEqual(self.student_client.get(reverse('ai_chat',args=[mine.pk])).status_code,404)
        self.assertEqual(self.student_client.post(reverse('ai_chat',args=[mine.pk]),{'question':'继续','request_id':uuid.uuid4()}).status_code,404)
        self.assertEqual(self.student_client.post(self.delete_url(mine),{'confirm':'yes'}).status_code,404)

    def test_cross_account_access_cannot_view_or_delete_and_login_is_required(self):
        conversation = self.chat()
        for client in [self.teacher_client,self.other_client,self.peer_client]:
            self.assertEqual(client.get(self.delete_url(conversation)).status_code,404)
            self.assertEqual(client.post(self.delete_url(conversation),{'confirm':'yes'}).status_code,404)
        self.assertEqual(self.client.post(self.delete_url(conversation),{'confirm':'yes'}).status_code,302)
        self.assertTrue(AIConversation.objects.filter(pk=conversation.pk).exists())
        teacher_chat = self.chat(user=self.teacher)
        self.assertRedirects(self.teacher_client.post(self.delete_url(teacher_chat),{'confirm':'yes'}),reverse('mathai'))

    def test_delete_requires_csrf_and_confirmation_escapes_title(self):
        conversation = self.chat()
        conversation.title='<script>alert(1)</script>';conversation.save()
        client = Client(enforce_csrf_checks=True);client.force_login(self.student)
        page = client.get(self.delete_url(conversation))
        self.assertNotContains(page,'<script>alert(1)</script>')
        self.assertEqual(client.post(self.delete_url(conversation),{'confirm':'yes'}).status_code,403)
        token = client.cookies['csrftoken'].value
        self.assertRedirects(client.post(self.delete_url(conversation),{'confirm':'yes','csrfmiddlewaretoken':token}),reverse('mathai'))

    def test_pending_answer_prevents_deletion_until_request_has_expired(self):
        conversation = self.chat()
        turn = AITurn.objects.get();turn.status='pending';turn.save()
        self.assertEqual(self.student_client.post(self.delete_url(conversation),{'confirm':'yes'}).status_code,409)
        self.assertTrue(AIConversation.objects.filter(pk=conversation.pk).exists())
        AITurn.objects.filter(pk=turn.pk).update(created_at=timezone.now()-timedelta(seconds=100))
        self.assertRedirects(self.student_client.post(self.delete_url(conversation),{'confirm':'yes'}),reverse('mathai'))

    def test_owner_can_remove_chat_from_a_deleted_class_without_removing_class(self):
        conversation = self.chat(lesson=self.lesson)
        self.lesson.deleted_at=timezone.now();self.lesson.save()
        self.assertEqual(self.student_client.get(reverse('ai_chat',args=[conversation.pk])).status_code,404)
        self.assertRedirects(self.student_client.post(self.delete_url(conversation),{'confirm':'yes'}),reverse('mathai'))
        self.assertTrue(Lesson.objects.filter(pk=self.lesson.pk).exists())

    @override_settings(MATHAI_PROVIDERS=ai_fixtures.CONFIG,MATHAI_DAILY_USER_LIMIT=1)
    def test_deleted_paid_chat_does_not_reset_user_daily_quota(self):
        token = uuid.uuid4()
        with patch('feedback.ai_views.remote_answer',return_value=('模型回答',[])) as remote:
            self.ask(provider='deepseek',request_id=token)
            self.ask(provider='deepseek',request_id=token)
            conversation = AIConversation.objects.get()
            self.student_client.post(self.delete_url(conversation),{'confirm':'yes'})
            self.assertEqual(AIUsageDay.objects.get().requests,1)
            self.assertEqual(self.ask(provider='deepseek').status_code,200)
            self.assertEqual(remote.call_count,1)
        self.assertFalse(AIConversation.objects.exists())
        self.assertEqual(self.ask().status_code,302)

    @override_settings(MATHAI_PROVIDERS=ai_fixtures.CONFIG,MATHAI_DAILY_GLOBAL_LIMIT=1)
    def test_deleted_paid_chat_does_not_reset_global_daily_quota(self):
        with patch('feedback.ai_views.remote_answer',return_value=('模型回答',[])) as remote:
            self.ask(provider='deepseek')
            self.student_client.post(self.delete_url(AIConversation.objects.get()),{'confirm':'yes'})
            self.assertEqual(self.ask(client=self.peer_client,provider='deepseek').status_code,200)
            self.assertEqual(remote.call_count,1)
        self.assertEqual(AIUsageDay.objects.get().requests,1)
