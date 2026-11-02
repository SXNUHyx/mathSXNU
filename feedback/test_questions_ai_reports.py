import io
import json
import uuid
from datetime import timedelta
from unittest.mock import patch, MagicMock
from urllib.error import HTTPError, URLError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.utils import timezone
from docx import Document
from . import test_course_features as fixtures
from .models import Response, ResponseEvent, QuestionAttachment, KnowledgeBlock, TeacherReply, AIConversation, AITurn
from .insights import keyword_insights
from .mathai import remote_answer, ProviderError, NoRedirect

CONFIG = {'deepseek':{'key':'unit-test-private-key','model':'deepseek-chat'}}


class QuestionReportTests(TestCase):
    setUp = fixtures.CourseFeatureTests.setUp
    feedback = fixtures.CourseFeatureTests.feedback
    reply = fixtures.CourseFeatureTests.reply

    def test_student_formula_multiple_files_and_question_history_survive_updates(self):
        block = KnowledgeBlock.objects.create(lesson=self.lesson,title='方差',body='描述波动')
        self.assertEqual(self.feedback(note=r'为什么 \(\operatorname{Var}(X)\) 这样定义？',block=block.pk,
            attachments=[fixtures.picture(),SimpleUploadedFile('题目.pdf',b'%PDF-1.7\nfixture')]).status_code,302)
        event = ResponseEvent.objects.get()
        self.assertEqual(event.block_title,'知识点 · 方差')
        self.assertEqual(event.attachments.count(),2)
        self.feedback(note='更新的问题')
        self.assertEqual(ResponseEvent.objects.count(),2)
        self.assertEqual(QuestionAttachment.objects.count(),2)
        self.assertContains(self.student_client.get(self.class_url),'题目.pdf')
        self.assertContains(self.student_client.get(self.class_url),'latex-editor')
        response = Response.objects.get()
        page = self.teacher_client.get(reverse('reply_create',args=[self.lesson.code,response.pk])+f'?event={event.pk}')
        self.assertEqual(page.context['question'].pk,event.pk)
        self.assertContains(page,'题目.pdf')
        self.reply(text='解释原来的问题',event_id=event.pk)
        payload = self.student_client.get(reverse('student_updates',args=[self.lesson.code])).json()
        self.assertEqual(len(payload['replies'][0]['attachments']),2)
        self.assertEqual(payload['replies'][0]['question'],event.note)

    def test_attachment_permissions_and_classroom_deletion(self):
        self.feedback(attachments=[fixtures.picture()])
        attachment = QuestionAttachment.objects.get()
        url = reverse('question_file',args=[attachment.pk])
        for client,status in [(self.client,302),(self.peer_client,404),(self.other_client,404)]:
            self.assertEqual(client.get(url).status_code,status)
        self.peer_client.get(self.class_url)
        self.assertEqual(self.peer_client.get(url).status_code,404)
        for client in [self.student_client,self.teacher_client]:
            result=client.get(url)
            self.assertEqual(result.status_code,200)
            self.assertEqual(result['Content-Type'],'image/png')
            result.close()
        self.teacher_client.post(reverse('lesson_delete',args=[self.lesson.code]),{'confirm':'yes'})
        self.assertEqual(self.student_client.get(url).status_code,404)
        self.teacher_client.post(reverse('lesson_restore',args=[self.lesson.code]))
        result=self.student_client.get(url);self.assertEqual(result.status_code,200);result.close()

    def test_all_files_validate_before_any_database_or_storage_write(self):
        for files in [[fixtures.picture(),SimpleUploadedFile('bad.png',b'not an image')],
                      [fixtures.picture() for _ in range(4)]]:
            self.assertEqual(self.feedback(attachments=files).status_code,400)
            self.assertFalse(ResponseEvent.objects.exists())
            self.assertFalse(QuestionAttachment.objects.exists())
        oversized = SimpleUploadedFile('large.pdf',b'%PDF-1.7\nfixture'); oversized.size=26*1024*1024
        # Unit-test field limit without sending a 26MB multipart body.
        from .forms import QuestionFilesField
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError): QuestionFilesField(required=False).clean([oversized])

    def test_topic_from_another_class_and_closed_class_reject_files(self):
        block=KnowledgeBlock.objects.create(lesson=self.other_lesson,title='私有模块')
        self.assertEqual(self.feedback(block=block.pk,attachments=[fixtures.picture()]).status_code,400)
        self.lesson.is_open=False;self.lesson.save()
        self.assertEqual(self.feedback(attachments=[fixtures.picture()]).status_code,400)
        self.assertFalse(QuestionAttachment.objects.exists())

    def test_attachment_only_creates_snapshot_and_identical_status_retry_does_not(self):
        self.feedback(note='',attachments=[fixtures.picture()])
        self.feedback(note='')
        self.assertEqual(ResponseEvent.objects.count(),1)
        self.feedback(note='',attachments=[fixtures.picture()])
        self.assertEqual(ResponseEvent.objects.count(),2)
        self.assertEqual(QuestionAttachment.objects.count(),2)

    def test_teacher_live_payload_includes_private_latest_attachments(self):
        self.feedback(attachments=[fixtures.picture()])
        payload=self.teacher_client.get(reverse('lesson_stats',args=[self.lesson.code])).json()
        self.assertEqual(len(payload['notes'][0]['attachments']),1)
        self.assertTrue(payload['notes'][0]['attachments'][0]['url'].startswith('/questions/files/'))
        self.assertEqual(self.student_client.get(reverse('lesson_stats',args=[self.lesson.code])).status_code,403)

    def test_keyword_counts_unique_students_current_yellow_red_only(self):
        self.feedback(note='方差为什么要平方？')
        self.feedback(note='方差方差与标准差的区别')
        self.peer_client.post(self.class_url,{'status':'yellow','real_name':'李同学','student_number':'2','note':'方差的含义是什么'})
        data=keyword_insights(self.lesson.responses.select_related('block'))
        self.assertEqual(data['students'],2)
        self.assertEqual(next(t['count'] for t in data['terms'] if t['term']=='方差'),2)
        self.feedback(status='green',note='方差已经理解')
        data=keyword_insights(self.lesson.responses.select_related('block'))
        self.assertEqual(data['students'],1)
        self.assertEqual(next(t['count'] for t in data['terms'] if t['term']=='方差'),1)

    def test_archive_natural_student_sort_history_replies_images_and_private_ai_excluded(self):
        self.feedback(student_number='0010',note='原问题',attachments=[fixtures.picture()])
        self.reply(text='第一轮解释')
        self.feedback(note='追问内容',student_number='0010')
        self.reply(text='第二轮解释')
        self.peer_client.post(self.class_url,{'status':'red','real_name':'李同学','student_number':'0002','note':'方差的疑问'})
        ai=AIConversation.objects.create(user=self.student,title='私人会话')
        AITurn.objects.create(conversation=ai,request_id=uuid.uuid4(),question='PRIVATE_AI_QUESTION',answer='私人问答',status='complete')
        result=self.teacher_client.get(reverse('export_answers',args=[self.lesson.code]))
        self.assertEqual(result.status_code,200)
        document=Document(io.BytesIO(result.content))
        text='\n'.join(p.text for p in document.paragraphs)
        self.assertLess(text.index('学号 0002'),text.index('学号 0010'))
        for expected in ['原问题','追问内容','第一轮解释','第二轮解释','知识点.png']:
            self.assertIn(expected,text)
        self.assertNotIn('PRIVATE_AI_QUESTION',text)
        self.assertEqual(len(document.inline_shapes),1)
        page=self.teacher_client.get(reverse('answer_report',args=[self.lesson.code]))
        self.assertContains(page,'打印 / 保存PDF')
        self.assertContains(page,'第二轮解释')

    def test_historical_hotspots_remain_after_resolution_and_deduplicate_repeat_questions(self):
        block=KnowledgeBlock.objects.create(lesson=self.lesson,title='方差的含义')
        self.feedback(note='方差是什么',block=block.pk)
        self.feedback(note='方差怎么计算',block=block.pk)
        self.feedback(status='green',note='已经理解',block=block.pk)
        data=keyword_insights(self.lesson.events.select_related('block'))
        self.assertEqual(data['students'],1)
        self.assertEqual(next(term['count'] for term in data['terms'] if term['term']=='方差'),1)
        block.delete()
        page=self.teacher_client.get(reverse('answer_report',args=[self.lesson.code]))
        self.assertEqual(page.context['insights']['students'],1)
        self.assertContains(page,'知识点 · 方差的含义')
        self.assertEqual(keyword_insights(self.lesson.responses.all())['students'],0)

    def test_archive_permissions_and_xss_safe_text(self):
        self.feedback(note='<script>alert(1)</script>')
        for route in ['answer_report','export_answers']:
            url=reverse(route,args=[self.lesson.code])
            self.assertEqual(self.student_client.get(url).status_code,403)
            self.assertEqual(self.other_client.get(url).status_code,404)
        self.assertNotContains(self.teacher_client.get(reverse('answer_report',args=[self.lesson.code])),'<script>alert(1)</script>')
        self.assertEqual(self.teacher_client.get(reverse('export_answers',args=[self.lesson.code])).status_code,200)

    def test_word_export_keeps_xml_control_characters_from_breaking_download(self):
        self.feedback(note='可读文字')
        Response.objects.update(note='可读文字\x00\x01')
        ResponseEvent.objects.update(note='可读文字\x00\x01')
        result=self.teacher_client.get(reverse('export_answers',args=[self.lesson.code]))
        self.assertEqual(result.status_code,200)
        self.assertIn('可读文字','\n'.join(p.text for p in Document(io.BytesIO(result.content)).paragraphs))


class MathAITests(TestCase):
    setUp = fixtures.CourseFeatureTests.setUp

    def ask(self,client=None,**fields):
        return (client or self.student_client).post(reverse('mathai'),{'provider':'local','request_id':str(uuid.uuid4()),'question':'方差是什么意思',**fields})

    def test_default_local_retrieval_and_citations_are_access_controlled(self):
        KnowledgeBlock.objects.create(lesson=self.lesson,title='方差',body=r'方差描述波动：\(E(X^2)-E(X)^2\)')
        KnowledgeBlock.objects.create(lesson=self.other_lesson,title='方差',body='SECRET_OTHER_COURSE')
        self.student_client.get(self.class_url)
        result=self.ask(lesson=self.lesson.pk)
        turn=AITurn.objects.get()
        self.assertEqual(turn.status,'complete')
        self.assertIn('方差描述波动',turn.answer)
        self.assertNotIn('SECRET_OTHER_COURSE',turn.answer)
        self.assertEqual(len(turn.sources),1)
        page=self.student_client.get(result.url)
        self.assertContains(page,'MathAI')
        self.assertNotContains(page,'本地 MathAI · 课程检索（非大模型）')
        self.assertContains(page,'方差描述波动')
        self.assertContains(page,'未配置',count=3)

    def test_teacher_and_student_have_separate_private_threads(self):
        self.student_client.get(self.class_url)
        self.ask()
        chat=AIConversation.objects.get()
        url=reverse('ai_chat',args=[chat.pk])
        for client in [self.teacher_client,self.peer_client,self.other_client]:
            self.assertEqual(client.get(url).status_code,404)
            self.assertEqual(client.post(url,{'question':'偷看','request_id':uuid.uuid4()}).status_code,404)
        self.assertEqual(self.ask(client=self.teacher_client).status_code,302)
        self.assertEqual(AIConversation.objects.count(),2)

    def test_unknown_remote_provider_or_foreign_lesson_cannot_be_submitted(self):
        self.assertEqual(self.ask(provider='deepseek').status_code,200)
        self.assertEqual(self.ask(lesson=self.other_lesson.pk).status_code,200)
        self.assertFalse(AIConversation.objects.exists())

    def test_missing_match_has_honest_fallback_and_never_calls_external_service(self):
        with patch('feedback.ai_views.remote_answer') as remote:
            self.ask(question='无匹配内容')
            remote.assert_not_called()
        self.assertIn('未找到',AITurn.objects.get().answer)
        self.assertIn('按课程文字匹配',AITurn.objects.get().answer)

    def test_same_request_id_is_idempotent_and_cannot_be_replayed_by_peer(self):
        token=uuid.uuid4()
        self.ask(request_id=token)
        self.ask(request_id=token)
        self.assertEqual(AITurn.objects.count(),1)
        self.assertEqual(self.ask(client=self.peer_client,request_id=token).status_code,404)

    @override_settings(MATHAI_PROVIDERS=CONFIG,MATHAI_DAILY_USER_LIMIT=1)
    def test_provider_is_server_configured_private_key_never_rendered_and_quota_enforced(self):
        with patch('feedback.ai_views.remote_answer',return_value=('测试模型回答',[])) as remote:
            result=self.ask(provider='deepseek')
            self.assertEqual(remote.call_count,1)
            self.assertContains(self.student_client.get(result.url),'测试模型回答')
            self.assertNotContains(self.student_client.get(result.url),'unit-test-private-key')
            self.ask(provider='deepseek')
            self.assertEqual(remote.call_count,1)
        self.assertEqual(AITurn.objects.count(),1)
        self.assertEqual(self.ask().status_code,302)

    @override_settings(MATHAI_PROVIDERS=CONFIG,MATHAI_DAILY_GLOBAL_LIMIT=1)
    def test_global_quota_blocks_new_accounts_and_provider_errors_are_saved(self):
        with patch('feedback.ai_views.remote_answer',side_effect=ProviderError('测试失败')) as remote:
            self.ask(provider='deepseek')
            self.assertEqual(AITurn.objects.get().status,'error')
            self.ask(client=self.peer_client,provider='deepseek')
            self.assertEqual(remote.call_count,1)

    def test_pending_timeout_releases_lock_and_new_request_can_complete(self):
        chat=AIConversation.objects.create(user=self.student,title='中断会话')
        old=AITurn.objects.create(conversation=chat,request_id=uuid.uuid4(),question='旧问题')
        result=self.ask()
        self.assertEqual(result.status_code,200)
        self.assertEqual(AITurn.objects.count(),1)
        AITurn.objects.filter(pk=old.pk).update(created_at=timezone.now()-timedelta(seconds=100))
        self.assertEqual(self.ask().status_code,302)
        old.refresh_from_db();self.assertEqual(old.status,'error')

    def test_deleted_lesson_hides_associated_chat(self):
        self.student_client.get(self.class_url)
        self.ask(lesson=self.lesson.pk)
        chat=AIConversation.objects.get()
        self.lesson.deleted_at=timezone.now();self.lesson.save()
        self.assertEqual(self.student_client.get(reverse('ai_chat',args=[chat.pk])).status_code,404)

    def test_ai_csrf_and_answer_html_are_safe(self):
        client=Client(enforce_csrf_checks=True);client.force_login(self.student)
        self.assertEqual(client.post(reverse('mathai'),{'question':'x'}).status_code,403)
        self.ask(question='<script>bad()</script>')
        chat=AIConversation.objects.get()
        AITurn.objects.update(answer='<img src=x onerror=bad()>')
        page=self.student_client.get(reverse('ai_chat',args=[chat.pk]))
        self.assertNotContains(page,'<script>bad()</script>')
        self.assertNotContains(page,'<img src=x onerror=bad()>')

    @override_settings(MATHAI_PROVIDERS=CONFIG)
    def test_real_adapter_payload_history_and_course_opt_in(self):
        self.student_client.get(self.class_url)
        KnowledgeBlock.objects.create(lesson=self.lesson,title='方差',body='本课堂方差讲解')
        chat=AIConversation.objects.create(user=self.student,lesson=self.lesson,provider='deepseek',title='测试')
        AITurn.objects.create(conversation=chat,request_id=uuid.uuid4(),question='上一问',answer='上一答',status='complete')
        opener=MagicMock()
        opener.open.return_value.__enter__.return_value.read.return_value=json.dumps({'choices':[{'message':{'content':'真实适配器测试回答'}}]}).encode()
        with patch('feedback.mathai.build_opener',return_value=opener):
            answer,_=remote_answer(chat,'方差是什么')
            self.assertEqual(answer,'真实适配器测试回答')
            payload=json.loads(opener.open.call_args.args[0].data)
            self.assertNotIn('本课堂方差讲解',json.dumps(payload,ensure_ascii=False))
            self.assertIn('上一答',json.dumps(payload,ensure_ascii=False))
            chat.share_course=True
            remote_answer(chat,'方差是什么')
            payload=json.loads(opener.open.call_args.args[0].data)
            self.assertIn('本课堂方差讲解',json.dumps(payload,ensure_ascii=False))

    @override_settings(MATHAI_PROVIDERS=CONFIG)
    def test_adapter_never_exposes_service_exception_bodies_and_does_not_redirect_keys(self):
        chat=AIConversation.objects.create(user=self.student,provider='deepseek',title='测试')
        for error in [HTTPError('https://service',401,'unit-test-private-key',{},None),URLError('unit-test-private-key')]:
            opener=MagicMock();opener.open.side_effect=error
            with patch('feedback.mathai.build_opener',return_value=opener),self.assertRaises(ProviderError) as caught:
                remote_answer(chat,'问题')
            self.assertNotIn('unit-test-private-key',str(caught.exception))
        self.assertIsNone(NoRedirect().redirect_request(None,None,302,'',{},'https://other.example/'))

    @override_settings(MATHAI_PROVIDERS=CONFIG)
    def test_remote_context_is_bounded_even_with_long_questions_and_history(self):
        chat=AIConversation.objects.create(user=self.student,provider='deepseek',title='长会话')
        for _ in range(8):
            AITurn.objects.create(conversation=chat,request_id=uuid.uuid4(),question='旧'*3000,answer='答'*20000,status='complete')
        opener=MagicMock()
        opener.open.return_value.__enter__.return_value.read.return_value=b'{"choices":[{"message":{"content":"ok"}}]}'
        with patch('feedback.mathai.build_opener',return_value=opener):
            remote_answer(chat,'新'*3000)
        payload=json.loads(opener.open.call_args.args[0].data)
        self.assertEqual(payload['messages'][-1]['content'],'新'*3000)
        self.assertLessEqual(sum(len(m['content']) for m in payload['messages']),4000)
