from django import forms
from django.contrib.auth.forms import SetPasswordForm
from .forms import RegistrationForm

ROLES = [('student','学生'),('teacher','教师'),('admin','开发者管理员')]


class Confirmed(forms.BooleanField):
    def to_python(self,value):
        return value is True or (isinstance(value,str) and value in ['True','true','yes','1','on'])


class UserFilters(forms.Form):
    q = forms.CharField(required=False,max_length=100,label='搜索账号 / 姓名 / 学号 / 邮箱')
    role = forms.ChoiceField(required=False,choices=[('','全部角色'),*ROLES])
    status = forms.ChoiceField(required=False,choices=[('','全部状态'),('active','已启用'),('inactive','已停用'),('archived','已归档')])
    page = forms.IntegerField(required=False,min_value=1)
    per_page = forms.ChoiceField(required=False,choices=[('25','25'),('50','50'),('100','100')])


class ProfileFields(forms.Form):
    real_name = forms.CharField(required=False,max_length=50,label='姓名（账号资料）')
    student_number = forms.RegexField(required=False,regex=r'^[A-Za-z0-9_-]{1,40}$',max_length=40,label='学号（账号资料）')
    email = forms.EmailField(required=False,max_length=254,label='邮箱（选填，未验证）')
    role = forms.ChoiceField(choices=ROLES,label='账号角色')
    reason = forms.CharField(required=False,max_length=300,label='操作备注（勿填写密码或验证码）',widget=forms.Textarea(attrs={'rows':2}))

    def clean_real_name(self):
        value=self.cleaned_data['real_name']
        if any(ord(c)<32 for c in value):
            raise forms.ValidationError('姓名不能包含控制字符。')
        return value


class CreateManagedUser(RegistrationForm,ProfileFields):
    password1 = forms.CharField(label='初始密码',strip=False,max_length=128,widget=forms.PasswordInput(attrs={'autocomplete':'new-password'}))
    password2 = forms.CharField(label='确认初始密码',strip=False,max_length=128,widget=forms.PasswordInput(attrs={'autocomplete':'new-password'}))

    class Meta(RegistrationForm.Meta):
        fields=['username','email']


class EditManagedUser(ProfileFields):
    confirm = Confirmed(widget=forms.HiddenInput,initial=True)


class AccountActionForm(forms.Form):
    reason = forms.CharField(required=False,max_length=300,label='操作备注（勿填写密码或验证码）',widget=forms.Textarea(attrs={'rows':2}))
    confirm = Confirmed(widget=forms.HiddenInput,initial=True)


class ResetManagedPassword(SetPasswordForm):
    new_password1 = forms.CharField(label='新密码',strip=False,max_length=128,widget=forms.PasswordInput(attrs={'autocomplete':'new-password'}))
    new_password2 = forms.CharField(label='确认新密码',strip=False,max_length=128,widget=forms.PasswordInput(attrs={'autocomplete':'new-password'}))
    current_password = forms.CharField(label='您当前的密码',strip=False,max_length=4096,widget=forms.PasswordInput(attrs={'autocomplete':'current-password'}))
    reason = forms.CharField(required=False,max_length=300,label='操作备注（勿填写密码或验证码）')
    confirm = Confirmed(widget=forms.HiddenInput,initial=True)

    def __init__(self,*args,require_current=False,**kwargs):
        self.require_current=require_current
        super().__init__(*args,**kwargs)
        if not require_current:
            self.fields.pop('current_password')

    def clean_current_password(self):
        value=self.cleaned_data['current_password']
        if not self.user.check_password(value):
            raise forms.ValidationError('当前密码不正确。')
        return value
