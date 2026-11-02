import uuid
from datetime import timedelta
from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q, Sum
from django.http import Http404, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods
from .models import AIConversation, AITurn, AccountProfile, AIUsageDay
from .mathai import available_lessons, provider_options, local_answer, remote_answer, ProviderError, PROVIDERS


class AIQuestionForm(forms.Form):
    provider = forms.ChoiceField(label='问答方式')
    lesson = forms.ModelChoiceField(queryset=None,required=False,label='关联课堂（选填）')
    share_course = forms.BooleanField(required=False,label='向外部模型附带相关课堂文字（选填）')
    question = forms.CharField(max_length=3000,label='您的问题',widget=forms.Textarea(attrs={'rows':4,'class':'latex-editor'}))
    request_id = forms.UUIDField(widget=forms.HiddenInput)

    def __init__(self,*args,user,conversation=None,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['provider'].choices = [(p['code'],p['label']) for p in provider_options() if p['ready']]
        self.fields['lesson'].queryset = available_lessons(user)
        self.fields['request_id'].initial = uuid.uuid4()
        if conversation:
            for key in ['provider','lesson','share_course']:
                self.fields.pop(key)


@login_required
@never_cache
def mathai(request, pk=None):
    eligible = AIConversation.objects.filter(user=request.user).filter(Q(lesson__isnull=True)|Q(lesson__in=available_lessons(request.user)))
    conversation = get_object_or_404(eligible,pk=pk) if pk else None
    form = AIQuestionForm(request.POST if request.method=='POST' else None,user=request.user,conversation=conversation)
    if not conversation and request.GET.get('lesson'):
        form.initial['lesson'] = available_lessons(request.user).filter(code=request.GET['lesson']).values_list('pk',flat=True).first()
    if request.method=='POST' and form.is_valid():
        data = form.cleaned_data
        existing = AITurn.objects.filter(request_id=data['request_id']).select_related('conversation').first()
        if existing:
            if existing.conversation.user_id != request.user.pk:
                raise Http404
            return redirect('ai_chat',pk=existing.conversation_id)
        # Reserve quota and idempotency token before outbound IO, never hold a DB
        # write transaction while waiting for a model. Profile serializes requests.
        error = None
        with transaction.atomic():
            profile,_ = AccountProfile.objects.get_or_create(user=request.user)
            AccountProfile.objects.select_for_update().get(pk=profile.pk)
            if conversation:
                conversation = get_object_or_404(eligible.select_for_update(),pk=conversation.pk)
            now = timezone.now()
            mine = AITurn.objects.filter(conversation__user=request.user)
            mine.filter(status='pending',created_at__lt=now-timedelta(seconds=90)).update(status='error',answer='此前请求中断，请重新提问。')
            existing = AITurn.objects.filter(request_id=data['request_id']).first()
            if existing:
                if existing.conversation.user_id != request.user.pk:
                    raise Http404
                return redirect('ai_chat',pk=existing.conversation_id)
            provider = conversation.provider if conversation else data['provider']
            day = timezone.localtime(now).date()
            paid = AIUsageDay.objects.filter(day=day)
            user_usage = paid.filter(user=request.user).values_list('requests',flat=True).first() or 0
            global_usage = paid.aggregate(total=Sum('requests'))['total'] or 0
            if mine.filter(status='pending').exists():
                error = '上一条问题仍在处理，请稍后再提问。'
            elif provider!='local' and (user_usage>=settings.MATHAI_DAILY_USER_LIMIT or global_usage>=settings.MATHAI_DAILY_GLOBAL_LIMIT):
                error = '今日模型调用次数已达上限，本地课程检索仍可使用。'
            elif conversation and conversation.turns.count()>=100:
                error = '本会话已有100次问答，请新建会话继续。'
            else:
                if not conversation:
                    conversation = AIConversation.objects.create(user=request.user,lesson=data['lesson'],provider=provider,
                        share_course=data['share_course'],title=data['question'][:80])
                turn = AITurn.objects.create(conversation=conversation,request_id=data['request_id'],question=data['question'])
                if provider!='local':
                    usage,_ = AIUsageDay.objects.get_or_create(user=request.user,day=day)
                    usage.requests += 1
                    usage.save(update_fields=['requests'])
        if error:
            form.add_error(None,error)
        else:
            try:
                if provider=='local':
                    answer,sources = local_answer(request.user,turn.question,conversation.lesson)
                else:
                    answer,sources = remote_answer(conversation,turn.question)
                AITurn.objects.filter(pk=turn.pk,status='pending').update(answer=answer,sources=sources,status='complete')
            except ProviderError as exc:
                AITurn.objects.filter(pk=turn.pk,status='pending').update(answer=str(exc),status='error')
            except Exception:
                # Preserve the question and release the reservation on failures.
                # Never expose exception bodies which could contain credentials.
                AITurn.objects.filter(pk=turn.pk,status='pending').update(answer='问答服务暂时异常，请稍后重试。',status='error')
            return redirect('ai_chat',pk=conversation.pk)
    threads = Paginator(eligible.select_related('lesson'),20).get_page(request.GET.get('page'))
    return render(request,'mathai.html',{'form':form,'conversation':conversation,'threads':threads,
        'turns':conversation.turns.all() if conversation else [],'providers':provider_options(),
        'provider_label':PROVIDERS.get(conversation.provider,('未知方式',''))[0] if conversation else '',
        'daily_limit':settings.MATHAI_DAILY_USER_LIMIT})


@login_required
@never_cache
@require_http_methods(['GET','POST'])
def delete_conversation(request, pk):
    # Ownership applies even when a classroom is now hidden or closed.
    conversation = get_object_or_404(AIConversation,pk=pk,user=request.user)
    if request.method=='POST':
        if request.POST.get('confirm')!='yes':
            return HttpResponseBadRequest('请确认删除会话。')
        with transaction.atomic():
            profile,_ = AccountProfile.objects.get_or_create(user=request.user)
            AccountProfile.objects.select_for_update().get(pk=profile.pk)
            conversation = get_object_or_404(AIConversation.objects.select_for_update(),pk=pk,user=request.user)
            if conversation.turns.filter(status='pending',created_at__gte=timezone.now()-timedelta(seconds=90)).exists():
                return render(request,'ai_conversation_delete.html',{'conversation':conversation,
                    'error':'该会话仍有问题正在处理，请稍后再删除。'},status=409)
            conversation.delete()
        messages.success(request,'会话及问答内容已删除。')
        return redirect('mathai')
    return render(request,'ai_conversation_delete.html',{'conversation':conversation})
