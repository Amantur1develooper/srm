from __future__ import annotations

from django import forms
from django.contrib.auth import get_user_model

from .models import Client, Comment, MessageTemplate, Stage, Task

User = get_user_model()


def _manager_qs():
    return User.objects.filter(is_active=True).order_by("first_name", "username")


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
    class Meta:
        model = Client
        fields = [
            "full_name", "phone", "phone_extra", "whatsapp_phone",
            "first_contact_date", "manager", "source", "stage",
            "looking_for", "budget", "next_step", "next_step_at", "comment",
        ]
        widgets = {
            "first_contact_date": forms.DateInput(attrs={"type": "date"}),
            "next_step_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "looking_for": forms.Textarea(attrs={"rows": 2}),
            "comment": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["manager"].queryset = _manager_qs()
        self.fields["stage"].queryset = Stage.objects.filter(is_active=True)
        if user is not None and not user.can_see_all_clients:
            self.fields["manager"].initial = user
            self.fields["manager"].disabled = True


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
