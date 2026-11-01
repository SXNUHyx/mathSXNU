from django import forms
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
