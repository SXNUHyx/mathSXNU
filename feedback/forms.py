from django import forms
import unicodedata
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from .models import Lesson, Response, KnowledgeBlock, CourseMaterial
from .uploads import inspect_upload


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class QuestionFilesField(forms.FileField):
    def clean(self, data, initial=None):
        files = data if isinstance(data, (list, tuple)) else ([data] if data else [])
        if len(files) > 3 or sum(getattr(f, 'size', 0) for f in files) > 25 * 1024 * 1024:
            raise forms.ValidationError('每次最多3个附件，合计不超过25MB。')
        cleaned = [super(QuestionFilesField, self).clean(f, initial) for f in files]
        for uploaded in cleaned:
            uploaded.inspected_type, uploaded.inspected_image = inspect_upload(uploaded)
        return cleaned


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
            "course": forms.TextInput(attrs={"placeholder": "请输入课程名称"}),
            "title": forms.TextInput(attrs={"placeholder": "请输入本次课堂主题"}),
        }


class ResponseForm(forms.Form):
    status = forms.ChoiceField(choices=Response.Status.choices)
    note = forms.CharField(max_length=3000, required=False, strip=True)
    block = forms.ModelChoiceField(queryset=KnowledgeBlock.objects.none(), required=False, label='相关模块（选填）')
    attachments = QuestionFilesField(required=False, label='图片或资料（选填）', widget=MultipleFileInput(attrs={'accept':'.jpg,.jpeg,.png,.webp,.pdf,.ppt,.pptx'}))
    real_name = forms.CharField(max_length=50, label="姓名")
    student_number = forms.RegexField(regex=r"^[A-Za-z0-9_-]{1,40}$", max_length=40, label="学号", error_messages={"invalid": "学号请使用数字、英文字母、下划线或连字符。"})

    def __init__(self, *args, lesson=None, **kwargs):
        super().__init__(*args, **kwargs)
        if lesson:
            self.fields['block'].queryset = lesson.blocks.all()

    def clean_real_name(self):
        value = self.cleaned_data["real_name"]
        if any(ord(c) < 32 for c in value):
            raise forms.ValidationError("姓名不能包含换行等控制字符。")
        return value


class RegistrationForm(UserCreationForm):
    username = forms.RegexField(
        regex=r"^\w{1,30}$", min_length=1, max_length=30, label="用户名（支持中文）",
        help_text="支持1—30位汉字、英文字母、数字或下划线，例如“王小明”；英文统一保存为小写。重名时可添加数字。",
        error_messages={"invalid": "用户名只能包含1—30位汉字、英文字母、数字或下划线。"},
        widget=forms.TextInput(attrs={"autocomplete": "username", "autocapitalize": "none"}),
    )

    class Meta(UserCreationForm.Meta):
        model = get_user_model()
        fields = ["username"]

    def clean_username(self):
        username = unicodedata.normalize("NFKC", self.cleaned_data["username"]).lower()
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


class KnowledgeBlockForm(forms.ModelForm):
    class Meta:
        model = KnowledgeBlock
        fields = ["kind", "title", "body", "position"]
        labels = {"kind": "模块类型", "title": "模块标题", "body": "内容（支持LaTeX）", "position": "排序（较小的排在前面）"}
        widgets = {"body": forms.Textarea(attrs={"rows": 8, "class": "latex-editor", "placeholder": r"可输入文字与公式，例如：\(\frac{a}{b}\)，独立公式使用 \[...\]"})}


class CourseMaterialForm(forms.ModelForm):
    class Meta:
        model = CourseMaterial
        fields = ["section", "title", "block", "file"]
        labels = {"section": "所属板块", "title": "资料或图片名称", "block": "板块内的模块（选填）", "file": "选择文件"}
        widgets = {"file": forms.FileInput(attrs={"accept": ".jpg,.jpeg,.png,.webp,.pdf,.ppt,.pptx"})}

    def __init__(self, *args, lesson, section=KnowledgeBlock.Kind.KNOWLEDGE, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["section"].choices = [(section, KnowledgeBlock.Kind(section).label)]
        self.fields["section"].initial = section
        # Also support old clients that did not submit a section field.
        if self.is_bound and not self.data.get("section"):
            self.data = self.data.copy()
            self.data["section"] = section
        self.fields["block"].queryset = lesson.blocks.filter(kind=section)
        self.fields["block"].empty_label = "放在本板块资料区（不关联具体模块）"

    def clean_file(self):
        uploaded = self.cleaned_data["file"]
        self.inspected_type, self.inspected_image = inspect_upload(uploaded)
        return uploaded


class ReplyForm(forms.Form):
    message = forms.CharField(max_length=5000, label="给学生的解释", widget=forms.Textarea(attrs={"rows": 4, "class": "latex-editor"}))
    event_id = forms.IntegerField(required=False, min_value=1, widget=forms.HiddenInput)
