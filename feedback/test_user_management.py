"""Developer console permissions, account lifecycle and data preservation."""
import csv
import io
import json
import uuid
from django.contrib.auth import get_user_model, HASH_SESSION_KEY
from django.core.exceptions import PermissionDenied
from django.core.management import call_command, CommandError
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone
from .models import AccountProfile, Lesson, ClassroomMembership, Response, ResponseEvent, AIConversation, UserManagementLog
from .user_management import update_user

PASSWORD='Lesson!Developer-8325-example'
NEW_PASSWORD='Fresh!Course-9271-example'


class UserManagementTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User=get_user_model()
        cls.admin=User.objects.create_superuser('开发管理员',password=PASSWORD)
        cls.teacher=User.objects.create_user('王老师',password=PASSWORD)
        AccountProfile.objects.create(user=cls.teacher,role='teacher',real_name='王老师')
        cls.student=User.objects.create_user('张同学',password=PASSWORD)
        AccountProfile.objects.create(user=cls.student,role='student',real_name='张同学',student_number='00123')
        cls.lesson=Lesson.objects.create(teacher=cls.teacher,course='微积分',title='极限')
        ClassroomMembership.objects.create(lesson=cls.lesson,student=cls.student)
        person=uuid.uuid4()
        cls.response=Response.objects.create(lesson=cls.lesson,user=cls.student,participant=person,status='red',note='原学习问题',real_name='原姓名',student_number='00001')
        cls.event=ResponseEvent.objects.create(lesson=cls.lesson,user=cls.student,participant=person,status='red',note='原学习问题',real_name='原姓名',student_number='00001')
        AIConversation.objects.create(user=cls.student,title='私有会话标题',provider='local')

    def setUp(self):
        self.client.force_login(self.admin)

    def api(self,name='developer_api_users',args=None,data=None,method='post',client=None):
        return getattr(client or self.client,method)(reverse(name,args=args),data=json.dumps(data or {}),content_type='application/json')

    def action(self,action,user=None,**extra):
        return self.api('developer_api_action',[user.pk if user else self.student.pk],{'action':action,'confirm':True,**extra})

    def test_console_and_detail_templates_render_and_do_not_leak_passwords(self):
        for name,args in [('developer_home',None),('developer_user_new',None),('developer_user',[self.student.pk]),('developer_audit',None),('developer_user_action',[self.student.pk,'password_reset'])]:
            with self.subTest(name=name):
                page=self.client.get(reverse(name,args=args))
                self.assertEqual(page.status_code,200)
                self.assertNotContains(page,PASSWORD)
                self.assertNotContains(page,self.student.password)
        self.assertContains(self.client.get(reverse('teacher_home')),'开发者管理')

    def test_anonymous_and_every_non_developer_role_are_denied(self):
        staff=get_user_model().objects.create_user('仅staff',is_staff=True)
        super_only=get_user_model().objects.create_user('仅super',is_superuser=True)
        urls=[('developer_api_users',None),('developer_api_user',[self.student.pk]),('developer_api_audit',None)]
        self.client.logout()
        for name,args in urls:
            self.assertEqual(self.client.get(reverse(name,args=args)).status_code,401)
        self.assertEqual(self.client.get(reverse('developer_home')).status_code,302)
        for user in [self.teacher,self.student,staff,super_only]:
            self.client.force_login(user)
            for name,args in urls:
                self.assertEqual(self.client.get(reverse(name,args=args)).status_code,403)
            self.assertEqual(self.client.get(reverse('developer_home')).status_code,403)
            self.assertEqual(self.action('disable',self.admin).status_code,403)
            self.assertNotContains(self.client.get(reverse('home')),'href="/developer/"')
        self.assertFalse(UserManagementLog.objects.exists())

    def test_api_methods_csrf_not_found_and_strict_input(self):
        self.assertEqual(self.client.delete(reverse('developer_api_users')).status_code,405)
        self.assertEqual(self.client.get(reverse('developer_api_user',args=[999999])).status_code,404)
        self.assertEqual(self.client.get(reverse('developer_api_action',args=[self.student.pk])).status_code,405)
        csrf=Client(enforce_csrf_checks=True);csrf.force_login(self.admin)
        rejected=self.api(data={'username':'csrf'},client=csrf)
        self.assertEqual(rejected.status_code,403)
        self.assertEqual(rejected.json()['error'],'csrf_failed')
        for data in [{'is_superuser':True},{'role':{'admin':True}},['bad'],{'username':'x'*66000}]:
            with self.subTest(data_type=type(data)):
                self.assertEqual(self.api(data=data).status_code,400)
        self.assertEqual(self.client.post(reverse('developer_api_users'),data='{',content_type='application/json').status_code,400)
        self.assertEqual(self.client.post(reverse('developer_api_users'),{'username':'bad'}).status_code,400)
        self.assertFalse(UserManagementLog.objects.exists())

    def test_list_filters_count_memberships_and_never_exposes_private_data(self):
        result=self.client.get(reverse('developer_api_users'),{'q':'00123','role':'student','status':'active'}).json()
        self.assertEqual(result['pagination']['total'],1)
        user=result['users'][0]
        self.assertEqual((user['username'],user['membership_count'],user['lesson_count']),('张同学',1,0))
        encoded=json.dumps(result,ensure_ascii=False)
        for secret in [self.student.password,'password','私有会话标题','原学习问题']:
            self.assertNotIn(secret,encoded)
        self.assertEqual(self.client.get(reverse('developer_api_users'),{'role':'teacher'}).json()['pagination']['total'],1)
        self.assertEqual(self.client.get(reverse('developer_api_users'),{'role':'admin'}).json()['pagination']['total'],1)
        self.assertEqual(self.client.get(reverse('developer_api_users'),{'q':'王老师'}).json()['users'][0]['id'],self.teacher.pk)
        for query in [{'page':'bad'},{'per_page':'99999'},{'status':'oops'}]:
            self.assertEqual(self.client.get(reverse('developer_api_users'),query).status_code,400)

    def test_missing_profiles_and_pagination_are_supported(self):
        get_user_model().objects.bulk_create([get_user_model()(username=f'legacy{i}') for i in range(30)])
        data=self.client.get(reverse('developer_api_users'),{'role':'student','per_page':25,'page':2}).json()
        self.assertEqual(data['pagination']['total'],31)
        self.assertEqual(len(data['users']),6)
        self.assertEqual(data['pagination']['pages'],2)

    def test_create_all_roles_chinese_names_hashes_and_audits(self):
        for role in ['student','teacher','admin']:
            result=self.api(data={'username':'新用户'+role,'role':role,'real_name':'李同学','student_number':'00029','email':'li@example.edu','password1':PASSWORD,'password2':PASSWORD,'reason':'新学期'})
            self.assertEqual(result.status_code,201,result.content)
            user=get_user_model().objects.get(pk=result.json()['user']['id'])
            self.assertTrue(user.check_password(PASSWORD))
            self.assertEqual(user.is_superuser,role=='admin')
            self.assertEqual(user.is_staff,role=='admin')
            self.assertEqual(user.account_profile.role,'student' if role=='student' else 'teacher')
            self.assertEqual(user.account_profile.real_name,'李同学')
            self.assertEqual(result.json()['user']['lesson_count'],0)
        self.assertEqual(UserManagementLog.objects.count(),3)
        log=UserManagementLog.objects.first()
        self.assertEqual(log.before,{})
        self.assertEqual(log.actor_id,self.admin.pk)
        self.assertEqual(log.reason,'新学期')
        self.assertNotIn(PASSWORD,json.dumps(log.after))

    def test_create_rejects_duplicate_weak_password_and_invalid_profiles(self):
        for extra in [{'username':'王老师'},{'password1':'12345678','password2':'12345678'},{'student_number':'<script>'},{'real_name':'坏\n姓名'},{'email':'invalid'}]:
            data={'username':'new_account','role':'student','password1':PASSWORD,'password2':PASSWORD,**extra}
            result=self.api(data=data)
            self.assertEqual(result.status_code,400,result.content)
        self.assertEqual(get_user_model().objects.count(),3)
        self.assertFalse(UserManagementLog.objects.exists())

    def test_edit_is_partial_and_historical_identity_is_preserved(self):
        result=self.api('developer_api_user',[self.student.pk],{'real_name':'新姓名','confirm':True},'patch')
        self.assertEqual(result.status_code,200,result.content)
        self.student.refresh_from_db();self.response.refresh_from_db();self.event.refresh_from_db()
        self.assertEqual(self.student.account_profile.real_name,'新姓名')
        self.assertEqual(self.student.account_profile.student_number,'00123')
        self.assertEqual(self.event.real_name,'原姓名')
        self.assertEqual(self.response.student_number,'00001')
        self.assertEqual(UserManagementLog.objects.get().before['real_name'],'张同学')
        self.assertEqual(UserManagementLog.objects.get().after['real_name'],'新姓名')

    def test_invalid_edits_do_not_create_empty_profiles_or_audits(self):
        user=get_user_model().objects.create_user('无资料')
        result=self.api('developer_api_user',[user.pk],{'role':'wrong','confirm':True},'patch')
        self.assertEqual(result.status_code,400)
        self.assertFalse(AccountProfile.objects.filter(user=user).exists())
        self.assertFalse(UserManagementLog.objects.exists())

    def test_teacher_with_even_deleted_classroom_cannot_become_student(self):
        for deleted in [None,timezone.now()]:
            Lesson.objects.filter(pk=self.lesson.pk).update(deleted_at=deleted)
            result=self.api('developer_api_user',[self.teacher.pk],{'role':'student','confirm':True},'patch')
            self.assertEqual(result.status_code,400)
            self.teacher.refresh_from_db()
            self.assertEqual(self.teacher.account_profile.role,'teacher')
        self.assertFalse(UserManagementLog.objects.exists())

    def test_admin_can_change_other_user_roles_but_cannot_demote_self(self):
        result=self.api('developer_api_user',[self.student.pk],{'role':'admin','confirm':True},'patch')
        self.assertEqual(result.status_code,200)
        self.student.refresh_from_db()
        other=Client();other.force_login(self.student)
        self.assertEqual(other.get(reverse('developer_home')).status_code,200)
        result=self.api('developer_api_user',[self.student.pk],{'role':'student','confirm':True},'patch')
        self.assertEqual(result.status_code,200)
        self.assertEqual(other.get(reverse('developer_home')).status_code,403)
        self.assertEqual(self.api('developer_api_user',[self.admin.pk],{'role':'teacher','confirm':True},'patch').status_code,400)
        self.admin.refresh_from_db();self.assertTrue(self.admin.is_superuser)

    def test_every_destructive_action_requires_true_confirmation(self):
        for confirm in [False,'false','no',0,None]:
            for action in ['disable','archive','enable']:
                self.assertEqual(self.action(action,confirm=confirm).status_code,400)
            self.assertEqual(self.api('developer_api_user',[self.student.pk],{'role':'teacher','confirm':confirm},'patch').status_code,400)
        self.student.refresh_from_db();self.assertTrue(self.student.is_active)
        self.assertFalse(UserManagementLog.objects.exists())

    def test_self_admin_cannot_be_disabled_or_archived(self):
        for action in ['disable','archive']:
            self.assertEqual(self.action(action,self.admin).status_code,400)
        self.assertEqual(self.client.get(reverse('developer_api_users')).json()['counts']['admins'],1)
        self.assertFalse(UserManagementLog.objects.exists())

    def test_archive_restore_enable_preserve_all_teaching_and_ai_records(self):
        peer=Client();peer.force_login(self.student)
        self.assertEqual(self.action('archive').status_code,200)
        self.student.refresh_from_db()
        self.assertFalse(self.student.is_active)
        self.assertIsNotNone(self.student.account_profile.archived_at)
        self.assertFalse(Client().login(username=self.student.username,password=PASSWORD))
        self.assertEqual(peer.get(reverse('student_home')).status_code,302)
        self.assertEqual(self.action('enable').status_code,400)
        self.assertEqual(self.action('password_reset',new_password1=NEW_PASSWORD,new_password2=NEW_PASSWORD).status_code,400)
        self.assertEqual(self.client.get(reverse('developer_api_users'),{'status':'archived'}).json()['pagination']['total'],1)
        self.assertEqual(self.action('restore').status_code,200)
        self.student.refresh_from_db()
        self.assertIsNone(self.student.account_profile.archived_at)
        self.assertFalse(self.student.is_active)
        self.assertEqual(self.action('enable').status_code,200)
        self.assertTrue(Client().login(username=self.student.username,password=PASSWORD))
        self.assertEqual((Lesson.objects.count(),ClassroomMembership.objects.count(),Response.objects.count(),ResponseEvent.objects.count(),AIConversation.objects.count()),(1,1,1,1,1))
        self.assertEqual(list(UserManagementLog.objects.order_by('pk').values_list('action',flat=True)),['archive','restore','enable'])

    def test_disable_existing_teacher_session_and_reenable(self):
        peer=Client();peer.force_login(self.teacher)
        self.assertEqual(self.action('disable',self.teacher).status_code,200)
        self.assertEqual(peer.get(reverse('teacher_home')).status_code,302)
        self.assertEqual(self.action('enable',self.teacher).status_code,200)
        self.assertTrue(peer.login(username=self.teacher.username,password=PASSWORD))

    def test_reset_password_invalidates_other_sessions_and_never_returns_password(self):
        peer=Client();peer.force_login(self.student)
        result=self.action('password_reset',new_password1=NEW_PASSWORD,new_password2=NEW_PASSWORD)
        self.assertEqual(result.status_code,200,result.content)
        self.student.refresh_from_db()
        self.assertTrue(self.student.check_password(NEW_PASSWORD))
        self.assertFalse(self.student.check_password(PASSWORD))
        self.assertEqual(peer.get(reverse('student_home')).status_code,302)
        serialized=json.dumps(self.client.get(reverse('developer_api_audit')).json())
        self.assertNotIn(NEW_PASSWORD,serialized)
        self.assertNotIn(self.student.password,serialized)
        self.assertNotIn('password1',serialized)

    def test_bad_password_reset_has_no_mutation(self):
        old_hash=self.student.password
        for new,confirmation in [('12345678','12345678'),(NEW_PASSWORD,'mismatch')]:
            self.assertEqual(self.action('password_reset',new_password1=new,new_password2=confirmation).status_code,400)
        self.student.refresh_from_db()
        self.assertEqual(self.student.password,old_hash)
        self.assertFalse(UserManagementLog.objects.exists())

    def test_self_reset_requires_current_password_keeps_only_current_session(self):
        peer=Client();peer.force_login(self.admin)
        self.assertEqual(self.action('password_reset',self.admin,new_password1=NEW_PASSWORD,new_password2=NEW_PASSWORD).status_code,400)
        self.assertEqual(self.action('password_reset',self.admin,new_password1=NEW_PASSWORD,new_password2=NEW_PASSWORD,current_password='wrong').status_code,400)
        result=self.action('password_reset',self.admin,new_password1=NEW_PASSWORD,new_password2=NEW_PASSWORD,current_password=PASSWORD)
        self.assertEqual(result.status_code,200,result.content)
        self.assertEqual(self.client.get(reverse('developer_home')).status_code,200)
        self.assertEqual(peer.get(reverse('developer_home')).status_code,302)

    def test_revoked_or_stale_actor_cannot_commit_even_with_cached_user(self):
        request=RequestFactory().post('/developer/')
        request.user=self.admin
        request.session={HASH_SESSION_KEY:self.admin.get_session_auth_hash()}
        get_user_model().objects.filter(pk=self.admin.pk).update(is_superuser=False)
        with self.assertRaises(PermissionDenied):
            update_user(request,self.student.pk,'disable',{'confirm':True})
        get_user_model().objects.filter(pk=self.admin.pk).update(is_superuser=True)
        request.session[HASH_SESSION_KEY]='stale-password-session'
        with self.assertRaises(PermissionDenied):
            update_user(request,self.student.pk,'disable',{'confirm':True})
        self.student.refresh_from_db();self.assertTrue(self.student.is_active)
        self.assertFalse(UserManagementLog.objects.exists())

    def test_mutation_get_only_displays_confirmation(self):
        for action in ['disable','archive','password_reset']:
            page=self.client.get(reverse('developer_user_action',args=[self.student.pk,action]))
            self.assertContains(page,'确认')
        self.student.refresh_from_db();self.assertTrue(self.student.is_active)
        self.assertFalse(UserManagementLog.objects.exists())

    def test_audit_is_searchable_and_csv_safely_exports_filtered_identity(self):
        self.api('developer_api_user',[self.student.pk],{'real_name':'=SUM(1+1)','confirm':True},'patch')
        result=self.client.get(reverse('developer_api_audit'),{'q':'张同学'}).json()
        self.assertEqual(result['pagination']['total'],1)
        self.assertEqual(result['records'][0]['actor'],'开发管理员')
        response=self.client.get(reverse('developer_export'),{'q':'00123'})
        rows=list(csv.reader(io.StringIO(response.content.decode('utf-8-sig'))))
        self.assertEqual(len(rows),2)
        self.assertEqual(rows[1][2],"'=SUM(1+1)")
        self.assertEqual(rows[1][3],'00123')
        self.assertNotIn(self.student.password,response.content.decode())

    def test_server_grant_existing_chinese_account_creates_audited_admin(self):
        output=io.StringIO()
        call_command('grant_platform_admin',username='王老师',stdout=output)
        self.teacher.refresh_from_db()
        self.assertTrue(self.teacher.is_staff and self.teacher.is_superuser and self.teacher.is_active)
        self.assertTrue(self.teacher.check_password(PASSWORD))
        self.assertNotIn(PASSWORD,output.getvalue())
        log=UserManagementLog.objects.get()
        self.assertEqual((log.actor,log.actor_name,log.action),(None,'服务器终端','grant_admin'))
        with self.assertRaises(CommandError):
            call_command('grant_platform_admin',username='不存在')
        user=get_user_model().objects.create_user('未设置密码')
        with self.assertRaises(CommandError):
            call_command('grant_platform_admin',username=user.username)

    def test_admin_login_keeps_developer_next_but_student_cannot_follow_it(self):
        self.client.logout()
        result=self.client.post(reverse('login'),{'username':self.admin.username,'password':PASSWORD,'next':reverse('developer_home')})
        self.assertRedirects(result,reverse('developer_home'))
        self.client.logout()
        result=self.client.post(reverse('login'),{'username':self.student.username,'password':PASSWORD,'next':reverse('developer_home')})
        self.assertRedirects(result,reverse('student_home'))

    def test_student_can_change_own_password_and_keeps_current_session(self):
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(reverse('password_change')).status_code,200)
        peer=Client();peer.force_login(self.student)
        result=self.client.post(reverse('password_change'),{'old_password':PASSWORD,'new_password1':NEW_PASSWORD,'new_password2':NEW_PASSWORD})
        self.assertRedirects(result,reverse('password_change_done'))
        self.assertEqual(self.client.get(reverse('student_home')).status_code,200)
        self.assertEqual(peer.get(reverse('student_home')).status_code,302)
        self.student.refresh_from_db();self.assertTrue(self.student.check_password(NEW_PASSWORD))
