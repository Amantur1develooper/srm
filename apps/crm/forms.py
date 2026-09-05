from __future__ import annotations

from django import forms
from django.contrib.auth import get_user_model

from .models import Client, Comment, Funnel, MessageTemplate, Stage, Task

User = get_user_model()


def _manager_qs():
    return User.objects.filter(is_active=True, role="manager").order_by("first_name", "username")


class BootstrapMixin:
    """Проставляет класс поля для единой стилизации."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in self.fields.values():
            w = f.widget
            css = "field-input"
            if isinstance(w, forms.CheckboxInput):
                css = "field-check"
            elif isinstance(w, (forms.Select, forms.SelectMultiple)):
                css = "field-input field-select"
            elif isinstance(w, forms.Textarea):
                css = "field-input field-textarea"
                w.attrs.setdefault("rows", 3)
            w.attrs["class"] = (w.attrs.get("class", "") + " " + css).strip()


class ClientForm(BootstrapMixin, forms.ModelForm):
    """Упрощённая карточка сделки: только поля из согласованной логики.

    Слева — кто это (ФИО по частям, телефон, менеджер).
    Справа — что по сделке (что ищет / что есть / комментарий).
    Дата обращения проставляется автоматически (см. views.client_create).
    """

    task_title = forms.CharField(
        label="Задача", required=False,
        widget=forms.TextInput(attrs={"placeholder": "Например: перезвонить"}),
    )
    task_date = forms.DateField(label="Дата", required=False, widget=forms.DateInput(attrs={"type": "date"}))

    class Meta:
        model = Client
        fields = [
            "last_name", "first_name", "middle_name", "phone", "manager", "source", "funnel",
            "looking_for", "what_has", "comment",
        ]
        widgets = {
            "looking_for": forms.Textarea(attrs={"rows": 2}),
            "what_has": forms.Textarea(attrs={"rows": 2}),
            "comment": forms.Textarea(attrs={"rows": 3}),
        }
        labels = {"looking_for": "Что ищет", "what_has": "Что есть", "source": "База", "funnel": "Воронка"}

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["manager"].queryset = _manager_qs()
        self.fields["funnel"].queryset = Funnel.objects.filter(is_active=True)
        self.fields["funnel"].required = False
        self.fields["source"].required = False
        self.fields["last_name"].widget.attrs["autofocus"] = True
        if user is not None and not user.can_see_all_clients:
            self.fields["manager"].initial = user
            self.fields["manager"].disabled = True

    def clean_source(self):
        return self.cleaned_data.get("source") or Client.Source.UNKNOWN

    def clean(self):
        cleaned = super().clean()
        # На новой сделке нужна хоть какая-то часть имени. Старые лиды (импорт, где
        # ФИО хранится одной строкой) редактируем и без фамилии/имени по частям.
        has_parts = cleaned.get("last_name") or cleaned.get("first_name")
        existing_full_name = self.instance.full_name if self.instance and self.instance.pk else ""
        if not has_parts and not existing_full_name:
            self.add_error("last_name", "Укажите фамилию или имя")
        return cleaned


class TaskForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Task
        fields = ["title", "client", "manager", "due_date", "due_time", "comment", "status"]
        widgets = {
            "due_date": forms.DateInput(attrs={"type": "date"}),
            "due_time": forms.TimeInput(attrs={"type": "time"}),
            "comment": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, user=None, client=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["manager"].queryset = _manager_qs()
        from .access import clients_for

        if user is not None:
            self.fields["client"].queryset = clients_for(user).order_by("full_name")
        if client is not None:
            self.fields["client"].initial = client
            self.fields["client"].widget = forms.HiddenInput()
        if user is not None and not user.can_see_all_clients:
            self.fields["manager"].initial = user


class QuickTaskForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Task
        fields = ["title", "due_date", "due_time", "comment"]
        widgets = {
            "due_date": forms.DateInput(attrs={"type": "date"}),
            "due_time": forms.TimeInput(attrs={"type": "time"}),
            "comment": forms.Textarea(attrs={"rows": 2}),
        }


class CommentForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Comment
        fields = ["text"]
        widgets = {"text": forms.Textarea(attrs={"rows": 2, "placeholder": "Новый комментарий…"})}


class MessageTemplateForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = MessageTemplate
        fields = ["name", "body", "is_active"]
        widgets = {"body": forms.Textarea(attrs={"rows": 6})}


class StageForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Stage
        fields = ["name", "slug", "order", "color", "is_active", "in_funnel", "is_won", "is_lost"]


class UserForm(BootstrapMixin, forms.ModelForm):
    password = forms.CharField(
        label="Пароль", required=False, widget=forms.PasswordInput,
        help_text="Оставьте пустым, чтобы не менять",
    )

    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "phone", "role", "is_active"]

    def save(self, commit=True):
        user = super().save(commit=False)
        pwd = self.cleaned_data.get("password")
        if pwd:
            user.set_password(pwd)
        if commit:
            user.save()
        return user


class ImportUploadForm(forms.Form):
    file = forms.FileField(label="Файл Excel (.xlsx)")

    def clean_file(self):
        f = self.cleaned_data["file"]
        if not f.name.lower().endswith(".xlsx"):
            raise forms.ValidationError("Нужен файл в формате .xlsx")
        if f.size > 15 * 1024 * 1024:
            raise forms.ValidationError("Файл больше 15 МБ")
        return f
