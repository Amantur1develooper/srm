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
        widget=forms.TextInput(attrs={"placeholder": "Выберите выше или напишите свою"}),
    )
    task_date = forms.DateField(label="Дата", required=False, widget=forms.DateInput(attrs={"type": "date"}))
    task_time = forms.TimeField(label="Время", required=False, widget=forms.TimeInput(attrs={"type": "time"}))
    # Стадия выбирается только при создании сделки; дальше её двигают в карточке/канбане.
    stage = forms.ModelChoiceField(label="Стадия", queryset=Stage.objects.none(), required=False, empty_label=None)

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
            # На телефоне открывается цифровая клавиатура набора номера.
            "phone": forms.TextInput(attrs={"type": "tel", "inputmode": "tel", "autocomplete": "tel"}),
        }
        labels = {"looking_for": "Что ищет", "what_has": "Что есть", "source": "База", "funnel": "Воронка"}

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["manager"].queryset = _manager_qs()
        self.fields["funnel"].queryset = Funnel.objects.filter(is_active=True)
        self.fields["funnel"].required = False
        self.fields["source"].required = False
        if self.instance.pk:
            del self.fields["stage"]
        else:
            # В окне «Новая сделка» только имя — фамилию/отчество не спрашиваем.
            del self.fields["last_name"]
            del self.fields["middle_name"]
            stages = Stage.objects.filter(is_active=True).order_by("order")
            self.fields["stage"].queryset = stages
            self.fields["stage"].initial = stages.filter(slug="new").first() or stages.first()
            # Менеджер по умолчанию — тот, кто заполняет.
            if user is not None and self.fields["manager"].queryset.filter(pk=user.pk).exists():
                self.fields["manager"].initial = user
        name_field = "last_name" if "last_name" in self.fields else "first_name"
        self.fields[name_field].widget.attrs["autofocus"] = True
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
            if "last_name" in self.fields:
                self.add_error("last_name", "Укажите фамилию или имя")
            else:
                self.add_error("first_name", "Укажите имя")
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

        self.fields["client"].required = False
        self.fields["client"].empty_label = "— без клиента —"
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
        fields = ["username", "first_name", "last_name", "phone", "role", "is_active", "can_access_finsovet"]
        widgets = {"phone": forms.TextInput(attrs={"type": "tel", "inputmode": "tel", "autocomplete": "tel"})}

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
