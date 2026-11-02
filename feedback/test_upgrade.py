"""Exercise the actual pre-registration -> registration database upgrade."""
import uuid
from django.contrib.auth.hashers import make_password
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.urls import reverse


class RegistrationUpgradeTests(TransactionTestCase):
    def test_existing_teachers_passwords_classrooms_and_anonymous_records_survive(self):
        old = [("feedback", "0002_loginthrottle")]
        new = MigrationExecutor(connection).loader.graph.leaf_nodes("feedback")
        self.addCleanup(lambda: MigrationExecutor(connection).migrate(new))
        executor = MigrationExecutor(connection)
        executor.migrate(old)
        apps = executor.loader.project_state(old).apps
        User = apps.get_model("auth", "User")
        Lesson = apps.get_model("feedback", "Lesson")
        Response = apps.get_model("feedback", "Response")
        Event = apps.get_model("feedback", "ResponseEvent")
        password_hash = make_password("OldTeacher!1428")
        user = User.objects.create(username="legacy_teacher", password=password_hash)
        lesson = Lesson.objects.create(teacher_id=user.pk, title="原来的课堂", code="ABC234")
        participant = uuid.uuid4()
        Response.objects.create(lesson_id=lesson.pk, participant=participant, status="red", note="升级前的留言")
        Event.objects.create(lesson_id=lesson.pk, participant=participant, status="red", note="升级前的留言")
        executor = MigrationExecutor(connection)
        executor.migrate(new)
        from .models import AccountProfile, Lesson as CurrentLesson, Response as CurrentResponse, ResponseEvent
        from django.contrib.auth import get_user_model
        current_user = get_user_model().objects.get(pk=user.pk)
        self.assertEqual(AccountProfile.objects.get(user_id=user.pk).role, "teacher")
        self.assertEqual(current_user.password, password_hash)
        self.assertTrue(current_user.check_password("OldTeacher!1428"))
        self.assertEqual(CurrentLesson.objects.get(pk=lesson.pk).title, "原来的课堂")
        self.assertEqual(CurrentResponse.objects.get().participant, participant)
        self.assertIsNone(CurrentResponse.objects.get().user_id)
        self.assertEqual(ResponseEvent.objects.get().note, "升级前的留言")
        result = self.client.post(reverse("login"), {"username": "legacy_teacher", "password": "OldTeacher!1428"})
        self.assertRedirects(result, reverse("teacher_home"))
        self.assertContains(self.client.get(reverse("dashboard", args=[lesson.code])), "原来的课堂")


class MaterialSectionUpgradeTests(TransactionTestCase):
    def test_existing_files_follow_module_kind_and_general_files_are_retained(self):
        old = [('feedback', '0005_accountprofile_real_name_and_more')]
        new = MigrationExecutor(connection).loader.graph.leaf_nodes('feedback')
        self.addCleanup(lambda: MigrationExecutor(connection).migrate(new))
        executor = MigrationExecutor(connection)
        executor.migrate(old)
        apps = executor.loader.project_state(old).apps
        user = apps.get_model('auth', 'User').objects.create(username='section_teacher')
        lesson = apps.get_model('feedback', 'Lesson').objects.create(teacher_id=user.pk, title='原课堂', code='ABC234')
        Block, Material = apps.get_model('feedback', 'KnowledgeBlock'), apps.get_model('feedback', 'CourseMaterial')
        original = []
        for kind in ['knowledge', 'key', 'difficult', None]:
            block = Block.objects.create(lesson_id=lesson.pk, title='原模块', kind=kind) if kind else None
            material = Material.objects.create(lesson_id=lesson.pk, block=block, title='原资料',
                file=f'lessons/{lesson.pk}/{kind}.pdf', original_name='原讲义.pdf', content_type='application/pdf', size=25)
            original.append((material.pk, str(material.file), kind or 'knowledge'))
        MigrationExecutor(connection).migrate(new)
        from .models import CourseMaterial
        for pk, path, section in original:
            material = CourseMaterial.objects.get(pk=pk)
            self.assertEqual(material.section, section)
            self.assertEqual(str(material.file), path)
            self.assertEqual(material.original_name, '原讲义.pdf')


class QuestionsAIUpgradeTests(TransactionTestCase):
    def test_previous_classroom_questions_and_teacher_replies_survive_new_tables(self):
        old=[('feedback','0006_material_sections')]
        new=MigrationExecutor(connection).loader.graph.leaf_nodes('feedback')
        self.addCleanup(lambda: MigrationExecutor(connection).migrate(new))
        executor=MigrationExecutor(connection);executor.migrate(old)
        apps=executor.loader.project_state(old).apps
        user=apps.get_model('auth','User').objects.create(username='prior_teacher')
        lesson=apps.get_model('feedback','Lesson').objects.create(teacher_id=user.pk,title='原答疑课堂',code='ABC234')
        person=uuid.uuid4()
        response=apps.get_model('feedback','Response').objects.create(lesson_id=lesson.pk,participant=person,status='red',note=r'原公式问题 \(x^2\)',student_number='0002')
        event=apps.get_model('feedback','ResponseEvent').objects.create(lesson_id=lesson.pk,participant=person,status='red',note=r'原公式问题 \(x^2\)',student_number='0002')
        apps.get_model('feedback','TeacherReply').objects.create(response_id=response.pk,teacher_id=user.pk,question_event_id=event.pk,question_text=event.note,message='原来的解释')
        MigrationExecutor(connection).migrate(new)
        from .models import Response,ResponseEvent,TeacherReply,QuestionAttachment,AITurn
        self.assertEqual(Response.objects.get().student_number,'0002')
        self.assertEqual(ResponseEvent.objects.get().note,r'原公式问题 \(x^2\)')
        self.assertEqual(TeacherReply.objects.get().message,'原来的解释')
        self.assertEqual(TeacherReply.objects.get().question_event_id,event.pk)
        self.assertFalse(QuestionAttachment.objects.exists())
        self.assertFalse(AITurn.objects.exists())


class MathAIUsageUpgradeTests(TransactionTestCase):
    def test_usage_backfill_preserves_old_chats_and_counts_china_calendar_days(self):
        from datetime import datetime, timezone as datetime_timezone, date
        old=[('feedback','0007_questions_mathai_archive')]
        new=MigrationExecutor(connection).loader.graph.leaf_nodes('feedback')
        self.addCleanup(lambda: MigrationExecutor(connection).migrate(new))
        executor=MigrationExecutor(connection);executor.migrate(old)
        apps=executor.loader.project_state(old).apps
        user=apps.get_model('auth','User').objects.create(username='usage_teacher')
        Conversation=apps.get_model('feedback','AIConversation')
        Turn=apps.get_model('feedback','AITurn')
        paid=Conversation.objects.create(user_id=user.pk,provider='deepseek',title='保留的旧会话')
        local=Conversation.objects.create(user_id=user.pk,provider='local',title='保留的本地会话')
        for provider,stamp,status in [(paid,datetime(2026,11,1,15,59,tzinfo=datetime_timezone.utc),'complete'),
                                      (paid,datetime(2026,11,1,16,1,tzinfo=datetime_timezone.utc),'error'),
                                      (paid,datetime(2026,11,1,17,0,tzinfo=datetime_timezone.utc),'pending'),
                                      (local,datetime(2026,11,1,17,0,tzinfo=datetime_timezone.utc),'complete')]:
            turn=Turn.objects.create(conversation=provider,request_id=uuid.uuid4(),question='原提问',answer='原答案',status=status)
            Turn.objects.filter(pk=turn.pk).update(created_at=stamp)
        MigrationExecutor(connection).migrate(new)
        from .models import AIConversation,AITurn,AIUsageDay
        self.assertEqual(AIConversation.objects.count(),2)
        self.assertEqual(AITurn.objects.count(),4)
        self.assertEqual(AITurn.objects.filter(answer='原答案').count(),4)
        self.assertEqual(AIUsageDay.objects.get(user_id=user.pk,day=date(2026,11,1)).requests,1)
        self.assertEqual(AIUsageDay.objects.get(user_id=user.pk,day=date(2026,11,2)).requests,2)
