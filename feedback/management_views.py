import csv
import io
import json
from functools import wraps
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied, ValidationError, RequestDataTooBig
from django.core.paginator import Paginator
from django.http import JsonResponse, HttpResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.csrf import csrf_failure as default_csrf_failure
from django.views.decorators.cache import never_cache
from .management_forms import UserFilters, CreateManagedUser
from .models import UserManagementLog
from .user_management import is_developer, list_payload, users_query, user_payload, filtered_users, create_user, update_user, action_form, ACTIONS


def developer_only(api=False):
    def decorate(view):
        @never_cache
        @wraps(view)
        def wrapped(request,*args,**kwargs):
            if not request.user.is_authenticated:
                if api:
                    return JsonResponse({'ok':False,'error':'login_required'},status=401)
                return redirect_to_login(request.get_full_path(),reverse('login'))
            if not is_developer(request.user):
                if api:
                    return JsonResponse({'ok':False,'error':'developer_required'},status=403)
                return render(request,'developer_required.html',status=403)
            try:
                return view(request,*args,**kwargs)
            except PermissionDenied:
                if api:
                    return JsonResponse({'ok':False,'error':'permission_denied'},status=403)
                raise
            except Http404:
                if api:
                    return JsonResponse({'ok':False,'error':'not_found'},status=404)
                raise
            except ValidationError as exc:
                if api:
                    return JsonResponse({'ok':False,'error':'invalid_data','errors':exc.messages},status=400)
                raise
            except RequestDataTooBig:
                if api:
                    return JsonResponse({'ok':False,'error':'request_too_large'},status=413)
                raise
        return wrapped
    return decorate


def csrf_failure(request,reason=''):
    if request.path.startswith('/developer/api/'):
        return JsonResponse({'ok':False,'error':'csrf_failed'},status=403)
    return default_csrf_failure(request,reason=reason)


def method_error(methods):
    response=JsonResponse({'ok':False,'error':'method_not_allowed'},status=405)
    response['Allow']=', '.join(methods)
    return response


def data_from_json(request,allowed):
    if request.content_type!='application/json':
        raise ValidationError('接口写入请使用application/json。')
    try:
        length=int(request.META.get('CONTENT_LENGTH') or 0)
    except (ValueError,TypeError):
        raise ValidationError('请求长度不正确。') from None
    if length<0 or length>65536 or len(request.body)>65536:
        raise ValidationError('请求内容过大。')
    try:
        data=json.loads(request.body)
    except (ValueError,UnicodeError):
        raise ValidationError('JSON格式不正确。') from None
    if not isinstance(data,dict) or set(data)-set(allowed):
        raise ValidationError('请求字段不符合接口定义。')
    if any(isinstance(value,(dict,list)) for value in data.values()):
        raise ValidationError('字段值必须是文本或布尔值。')
    return data


def form_error(form):
    return JsonResponse({'ok':False,'error':'invalid_data','errors':dict(form.errors)},status=400)


@developer_only()
def dashboard(request):
    if request.method!='GET':
        return method_error(['GET'])
    form=UserFilters(request.GET)
    valid=form.is_valid()
    payload=list_payload(form.cleaned_data if valid else {})
    return render(request,'developer_users.html',{'filter_form':form,'payload':payload},status=200 if valid else 400)


@developer_only()
def new_user(request):
    if request.method=='POST':
        user,form=create_user(request,request.POST)
        if user:
            messages.success(request,'账号已创建。请通过私密方式告知使用者初始密码。')
            return redirect('developer_user',pk=user.pk)
    elif request.method=='GET':
        form=CreateManagedUser(initial={'role':'student'})
    else:
        return method_error(['GET','POST'])
    return render(request,'developer_user_form.html',{'form':form,'creating':True})


@developer_only()
def user_detail(request,pk):
    user=get_object_or_404(users_query(),pk=pk)
    if request.method=='POST':
        result,form=update_user(request,pk,'edit',request.POST)
        if result:
            messages.success(request,'账号资料已更新；历史课堂身份快照保留。')
            return redirect('developer_user',pk=pk)
    elif request.method=='GET':
        form=action_form('edit',user,actor=request.user)
    else:
        return method_error(['GET','POST'])
    return render(request,'developer_user_form.html',{'form':form,'managed_user':user,'record':user_payload(user)})


@developer_only()
def user_action(request,pk,action):
    if action not in ['enable','disable','archive','restore','password_reset']:
        raise Http404
    user=get_object_or_404(users_query(),pk=pk)
    if request.method=='POST':
        result,form=update_user(request,pk,action,request.POST)
        if result:
            messages.success(request,ACTIONS[action]+'成功。')
            return redirect('developer_user',pk=pk)
    elif request.method=='GET':
        form=action_form(action,user,actor=request.user)
    else:
        return method_error(['GET','POST'])
    return render(request,'developer_user_action.html',{'form':form,'managed_user':user,'action':action,'action_label':ACTIONS[action]})


def audit_payload(query):
    form=UserFilters(query)
    if not form.is_valid():
        return None,form
    data=form.cleaned_data
    records=UserManagementLog.objects.all()
    if data.get('q'):
        from django.db.models import Q
        records=records.filter(Q(actor_name__icontains=data['q'])|Q(target_username__icontains=data['q']))
    page=Paginator(records,25).get_page(data.get('page') or 1)
    return {'ok':True,'records':[{'id':r.pk,'actor':r.actor_name,'target':r.target_username,'target_id':r.target_id_snapshot,
        'action':r.action,'action_label':ACTIONS.get(r.action,r.action),'before':r.before,'after':r.after,
        'reason':r.reason,'created_at':r.created_at.isoformat()} for r in page],
        'pagination':{'page':page.number,'pages':page.paginator.num_pages,'total':page.paginator.count}},form


@developer_only()
def audit_logs(request):
    if request.method!='GET':
        return method_error(['GET'])
    payload,form=audit_payload(request.GET)
    return render(request,'developer_audit.html',{'payload':payload,'filter_form':form},status=200 if payload else 400)


@developer_only()
def export_users(request):
    if request.method!='GET':
        return method_error(['GET'])
    from .views import csv_safe
    form=UserFilters(request.GET)
    if not form.is_valid():
        return form_error(form)
    output=io.StringIO();writer=csv.writer(output)
    writer.writerow(['用户ID','用户名','账号姓名','账号学号','邮箱','角色','状态','注册时间（北京时间）','最后登录（北京时间）'])
    from django.utils import timezone
    for user in filtered_users(form.cleaned_data).iterator(chunk_size=500):
        row=user_payload(user)
        writer.writerow([user.pk,*[csv_safe(row[key]) for key in ['username','real_name','student_number','email','role_label','status_label']],
            timezone.localtime(user.date_joined).strftime('%Y-%m-%d %H:%M:%S'),
            timezone.localtime(user.last_login).strftime('%Y-%m-%d %H:%M:%S') if user.last_login else ''])
    response=HttpResponse('\ufeff'+output.getvalue(),content_type='text/csv; charset=utf-8')
    response['Content-Disposition']='attachment; filename="platform-users.csv"'
    return response


@developer_only(api=True)
def api_users(request):
    if request.method=='GET':
        form=UserFilters(request.GET)
        return JsonResponse(list_payload(form.cleaned_data)) if form.is_valid() else form_error(form)
    if request.method=='POST':
        data=data_from_json(request,CreateManagedUser.base_fields)
        user,form=create_user(request,data)
        return JsonResponse({'ok':True,'user':user_payload(users_query().get(pk=user.pk))},status=201) if user else form_error(form)
    return method_error(['GET','POST'])


@developer_only(api=True)
def api_user_detail(request,pk):
    user=get_object_or_404(users_query(),pk=pk)
    if request.method=='GET':
        return JsonResponse({'ok':True,'user':user_payload(user)})
    if request.method=='PATCH':
        allowed=action_form('edit',user).fields
        data=data_from_json(request,allowed)
        # PATCH preserves omitted public profile values, never admin flags.
        initial={key:value for key,value in user_payload(user).items() if key in allowed}
        initial.update(data)
        result,form=update_user(request,pk,'edit',initial)
        return JsonResponse({'ok':True,'user':user_payload(users_query().get(pk=result.pk))}) if result else form_error(form)
    return method_error(['GET','PATCH'])


@developer_only(api=True)
def api_user_action(request,pk):
    if request.method!='POST':
        return method_error(['POST'])
    user=get_object_or_404(users_query(),pk=pk)
    common={'action','reason','confirm','new_password1','new_password2','current_password'}
    data=data_from_json(request,common)
    action=data.pop('action',None)
    if action not in ['enable','disable','archive','restore','password_reset']:
        raise ValidationError('不支持的账号操作。')
    if set(data)-set(action_form(action,user,actor=request.user).fields):
        raise ValidationError('该操作不接受这些字段。')
    result,form=update_user(request,pk,action,data)
    return JsonResponse({'ok':True,'user':user_payload(users_query().get(pk=result.pk))}) if result else form_error(form)


@developer_only(api=True)
def api_audit(request):
    if request.method!='GET':
        return method_error(['GET'])
    payload,form=audit_payload(request.GET)
    return JsonResponse(payload) if payload else form_error(form)
