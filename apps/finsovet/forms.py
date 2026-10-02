from django import forms

from apps.crm.forms import BootstrapMixin

from .access import responsible_people
from .models import Block, Question


class QuestionQuickForm(BootstrapMixin, forms.ModelForm):
    """«+ Добавить»: минимум — блок и сам вопрос. Остальное можно позже."""

    class Meta:
        model = Question
        fields = ["block", "title", "action", "due_date", "responsible"]
        widgets = {"due_date": forms.DateInput(attrs={"type": "date"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["action"].required = False
        self.fields["due_date"].required = False
        self.fields["responsible"].required = False
        self.fields["responsible"].queryset = responsible_people()
        self.fields["title"].label = "Вопрос"
        self.fields["action"].label = "Действие (можно позже)"
        self.fields["due_date"].label = "Срок (можно позже)"
        self.fields["responsible"].label = "Ответственный (можно позже)"


class CommentForm(BootstrapMixin, forms.Form):
    text = forms.CharField(label="Комментарий", widget=forms.Textarea(attrs={"rows": 2}))


class BlockForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Block
        fields = ["name", "slug", "order"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["slug"].required = False
        self.fields["slug"].help_text = "Можно оставить пустым — заполнится само"
        self.fields["order"].required = False

    def save(self, commit=True):
        obj = super().save(commit=False)
        if not obj.slug:
            import uuid

            obj.slug = f"block-{uuid.uuid4().hex[:8]}"
        if self.cleaned_data.get("order") is None:
            obj.order = 0
        if commit:
            obj.save()
        return obj
