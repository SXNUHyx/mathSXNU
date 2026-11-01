from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from .models import Lesson, Response


class JoinForm(forms.Form):
    code = forms.RegexField(
        regex=r"^[A-HJ-NP-Z2-9]{6}$", max_length=6, min_length=6,
        label="课堂码", error_messages={"invalid": "请输入正确的6位课堂码。"},
        widget=forms.TextInput(attrs={"placeholder": "例如 AB3K9M", "autocomplete": "off", "autocapitalize": "characters"}),
    )

    def clean_code(self):
        return self.cleaned_data["code"].upper()


class LessonForm(forms.ModelForm):
    expected_count = forms.IntegerField(label="预计参与人数（选填）", required=False, min_value=1, max_value=2000)

    class Meta:
        model = Lesson
        fields = ["course", "title", "expected_count"]
        labels = {"course": "课程名称", "title": "本次课堂 / 知识点"}
        widgets = {
            "course": forms.TextInput(attrs={"placeholder": "例如：高等数学 · 一年级"}),
            "title": forms.TextInput(attrs={"placeholder": "例如：连续与可导的关系"}),
        }


class ResponseForm(forms.Form):
    status = forms.ChoiceField(choices=Response.Status.choices)
    note = forms.CharField(max_length=300, required=False, strip=True)


class RegistrationForm(UserCreationForm):
    username = forms.RegexField(
        regex=r"^[A-Za-z0-9_]{3,30}$", min_length=3, max_length=30, label="用户名",
        help_text="使用3—30位英文字母、数字或下划线；注册后统一保存为小写。",
        error_messages={"invalid": "用户名只能包含3—30位英文字母、数字或下划线。"},
        widget=forms.TextInput(attrs={"autocomplete": "username", "autocapitalize": "none"}),
    )

    class Meta(UserCreationForm.Meta):
        model = get_user_model()
        fields = ["username"]

    def clean_username(self):
        username = self.cleaned_data["username"].lower()
        if get_user_model().objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("这个用户名已被使用，请换一个。")
        return username


class PlatformAuthenticationForm(AuthenticationForm):
    def clean_username(self):
        username = self.cleaned_data["username"]
        users = get_user_model().objects
        # Preserve exact legacy usernames, including an existing case-only pair.
        if users.filter(username=username).exists():
            return username
        matches = list(users.filter(username__iexact=username).values_list("username", flat=True)[:2])
        return matches[0] if len(matches) == 1 else username
