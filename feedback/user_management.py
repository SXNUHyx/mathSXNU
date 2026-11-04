"""Account operations shared by the developer UI, JSON API and server bootstrap."""
from django.contrib.auth import get_user_model, HASH_SESSION_KEY, update_session_auth_hash
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Q, Count
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from .models import AccountProfile, Lesson, UserManagementLog
from .management_forms import CreateManagedUser, EditManagedUser, AccountActionForm, ResetManagedPassword

ROLE_LABELS={'student':'学生','teacher':'教师','admin':'开发者管理员'}
ACTIONS={'create':'创建账号','edit':'修改资料/角色','enable':'启用账号','disable':'停用账号',
         'archive':'归档账号','restore':'恢复账号','password_reset':'重置密码','grant_admin':'服务器开通管理员'}


from .roles import is_developer


def profile_of(user):
    try:
        return user.account_profile
    except AccountProfile.DoesNotExist:
        return None


def role_of(user):
    profile=profile_of(user)
    if user.is_superuser:
        return 'admin'
    return 'teacher' if user.is_staff or (profile and profile.role=='teacher') else 'student'


def account_state(user):
    profile=profile_of(user)
    return {'username':user.username,'role':role_of(user),'is_active':user.is_active,'email':user.email,
            'real_name':profile.real_name if profile else '', 'student_number':profile.student_number if profile else '',
            'archived_at':profile.archived_at.isoformat() if profile and profile.archived_at else None}


def user_payload(user):
    result={'id':user.pk,**account_state(user),'date_joined':user.date_joined.isoformat(),
            'last_login':user.last_login.isoformat() if user.last_login else None}
    result['role_label']=ROLE_LABELS[result['role']]
    result['status']='archived' if result['archived_at'] else 'active' if user.is_active else 'inactive'
    result['status_label']={'archived':'已归档','active':'已启用','inactive':'已停用'}[result['status']]
    result['lesson_count']=getattr(user,'lesson_count',None)
    result['membership_count']=getattr(user,'membership_count',None)
    return result


def users_query():
    return get_user_model().objects.select_related('account_profile').annotate(
        lesson_count=Count('lesson',distinct=True),membership_count=Count('classroom_memberships',distinct=True))


def filtered_users(data):
    users=users_query()
    if data.get('q'):
        q=data['q'];users=users.filter(Q(username__icontains=q)|Q(email__icontains=q)|Q(account_profile__real_name__icontains=q)|Q(account_profile__student_number__icontains=q))
    if data.get('role')=='admin':
        users=users.filter(is_superuser=True)
    elif data.get('role')=='teacher':
        users=users.filter(is_superuser=False).filter(Q(is_staff=True)|Q(account_profile__role='teacher'))
    elif data.get('role')=='student':
        users=users.filter(is_superuser=False,is_staff=False).exclude(account_profile__role='teacher')
    if data.get('status')=='archived':
        users=users.filter(account_profile__archived_at__isnull=False)
    elif data.get('status') in ['active','inactive']:
        users=users.filter(account_profile__archived_at__isnull=True,is_active=data['status']=='active')
    return users.order_by('-date_joined','-pk')


def list_payload(data):
    page=Paginator(filtered_users(data),int(data.get('per_page') or 25)).get_page(data.get('page') or 1)
    users=get_user_model().objects
    archived=users.filter(account_profile__archived_at__isnull=False).count()
    return {'ok':True,'users':[user_payload(user) for user in page],
        'pagination':{'page':page.number,'pages':page.paginator.num_pages,'total':page.paginator.count,'per_page':page.paginator.per_page},
        'counts':{'total':users.count(),'active':users.filter(is_active=True,account_profile__archived_at__isnull=True).count(),
                  'archived':archived,'admins':users.filter(is_active=True,is_superuser=True,is_staff=True).count()}}


def fresh_actor(request):
    actor=get_object_or_404(get_user_model().objects.select_for_update(),pk=request.user.pk)
    if not is_developer(actor) or not constant_time_compare(request.session.get(HASH_SESSION_KEY,''),actor.get_session_auth_hash()):
        raise PermissionDenied('管理员会话已失效，请重新登录。')
    return actor


def audit(actor,target,action,before,reason='',actor_name=None):
    # Deliberately whitelist account_state: no passwords, hashes, keys or sessions.
    return UserManagementLog.objects.create(actor=actor,target=target,actor_name=actor_name or actor.username,
        target_username=target.username,target_id_snapshot=target.pk,action=action,before=before,
        after=account_state(target),reason=reason)


def apply_role(user,profile,role):
    user.is_superuser=role=='admin';user.is_staff=role=='admin'
    profile.role='teacher' if role in ['teacher','admin'] else 'student'


def create_user(request,data):
    form=CreateManagedUser(data)
    if not form.is_valid():
        return None,form
    user=form.save(commit=False)
    cleaned=form.cleaned_data
    user.email=cleaned['email']
    try:
        with transaction.atomic():
            actor=fresh_actor(request)
            profile=AccountProfile(user=user,real_name=cleaned['real_name'],student_number=cleaned['student_number'])
            apply_role(user,profile,cleaned['role'])
            user.save();profile.save()
            audit(actor,user,'create',{},cleaned['reason'])
    except IntegrityError:
        form.add_error('username','用户名已被使用，请换一个。')
        return None,form
    return user,form


def action_form(action,user,data=None,actor=None):
    if action=='edit':
        initial={k:v for k,v in account_state(user).items() if k in ['role','email','real_name','student_number']}
        return EditManagedUser(data,initial=initial)
    if action=='password_reset':
        return ResetManagedPassword(user=user,data=data,require_current=bool(actor and actor.pk==user.pk))
    return AccountActionForm(data)


def update_user(request,pk,action,data):
    if action not in ACTIONS or action in ['create','grant_admin']:
        raise ValidationError('不支持的管理操作。')
    with transaction.atomic():
        actor=fresh_actor(request)
        user=get_object_or_404(get_user_model().objects.select_for_update(),pk=pk)
        profile=profile_of(user) or AccountProfile(user=user)
        user.account_profile=profile
        form=action_form(action,user,data,actor)
        if not form.is_valid():
            return None,form
        before=account_state(user)
        cleaned=form.cleaned_data
        try:
            archived=profile.archived_at is not None
            if archived and action!='restore':
                raise ValidationError('请先恢复已归档账号，再执行其他操作。')
            removes_admin=action in ['disable','archive'] or (action=='edit' and cleaned['role']!='admin')
            if user.pk==actor.pk and removes_admin:
                raise ValidationError('不能停用、归档或降低当前登录管理员的权限。')
            if removes_admin and user.is_active and user.is_superuser and user.is_staff:
                admins=list(get_user_model().objects.select_for_update().filter(is_active=True,is_superuser=True,is_staff=True).values_list('pk',flat=True))
                if len(admins)<=1:
                    raise ValidationError('至少保留一个已启用的开发者管理员。')
            if action=='edit':
                if cleaned['role']=='student' and Lesson.objects.filter(teacher=user).exists():
                    raise ValidationError('此账号名下仍有课堂，不能直接改为学生；可保留教师角色或停用账号。')
                user.email=cleaned['email'];profile.real_name=cleaned['real_name'];profile.student_number=cleaned['student_number']
                apply_role(user,profile,cleaned['role'])
            elif action=='password_reset':
                user.set_password(cleaned['new_password1'])
            elif action=='enable':
                user.is_active=True
            elif action=='disable':
                user.is_active=False
            elif action=='archive':
                user.is_active=False;profile.archived_at=timezone.now()
            elif action=='restore':
                if not archived:
                    raise ValidationError('该账号未归档。')
                profile.archived_at=None;user.is_active=False
            user.save();profile.save()
            audit(actor,user,action,before,cleaned.get('reason',''))
        except ValidationError as exc:
            form.add_error(None,exc)
            return None,form
    if action=='password_reset' and user.pk==request.user.pk:
        update_session_auth_hash(request,user)
    return user,form
