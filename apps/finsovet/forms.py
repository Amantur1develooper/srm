from django import forms

from apps.crm.forms import BootstrapMixin

from .access import finsovet_members
from .models import Decision, Node, Section, Task


class NodeChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return obj.path


class QuickEntryForm(BootstrapMixin, forms.Form):
    """«+ ДОБАВИТЬ»: куда / что произошло / кто сообщил."""

    node = NodeChoiceField(
        queryset=Node.objects.filter(is_active=True).select_related("parent", "parent__parent"),
        label="Куда", empty_label="— выберите —",
    )
    text = forms.CharField(label="Что произошло", widget=forms.Textarea(attrs={"rows": 2}))
    reported_by = forms.ModelChoiceField(
        queryset=finsovet_members(), label="Кто сообщил", required=False, empty_label="Я",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["reported_by"].queryset = finsovet_members()


class StateUpdateForm(BootstrapMixin, forms.Form):
    text = forms.CharField(label="Новое состояние", widget=forms.Textarea(attrs={"rows": 2}))
    is_problem = forms.BooleanField(label="⚠ Это проблема", required=False)
    reported_by = forms.ModelChoiceField(
        queryset=finsovet_members(), label="Кто сообщил", required=False, empty_label="Я",
    )


class CommentForm(BootstrapMixin, forms.Form):
    text = forms.CharField(label="Комментарий", widget=forms.Textarea(attrs={"rows": 2}))
    reported_by = forms.ModelChoiceField(
        queryset=finsovet_members(), label="Автор", required=False, empty_label="Я",
    )


class TaskQuickForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Task
        fields = ["title", "assignee", "due_date"]
        widgets = {"due_date": forms.DateInput(attrs={"type": "date"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["assignee"].queryset = finsovet_members()
        self.fields["assignee"].required = False
        self.fields["title"].label = "Что сделать"
        self.fields["assignee"].label = "Кто"
        self.fields["due_date"].label = "Когда"


class DecisionForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Decision
        fields = ["text", "responsible", "due_date"]
        widgets = {"text": forms.Textarea(attrs={"rows": 2}), "due_date": forms.DateInput(attrs={"type": "date"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["responsible"].queryset = finsovet_members()
        self.fields["responsible"].required = False
        self.fields["text"].label = "Решение"


class NodeForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Node
        fields = ["section", "parent", "name", "order"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["parent"].queryset = Node.objects.filter(is_active=True).select_related("parent")
        self.fields["parent"].required = False
        self.fields["parent"].label_from_instance = lambda o: o.path


class SectionForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Section
        fields = ["name", "slug", "order"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["slug"].required = False
        self.fields["slug"].help_text = "Можно оставить пустым — заполнится само"

    def save(self, commit=True):
        obj = super().save(commit=False)
        if not obj.slug:
            import uuid

            obj.slug = f"section-{uuid.uuid4().hex[:8]}"
        if commit:
            obj.save()
        return obj
