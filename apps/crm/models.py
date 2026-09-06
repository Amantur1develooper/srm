"""Модели Webordo CRM.

Сущности спроектированы с прицелом на второй этап (WhatsApp Business API),
чтобы не переделывать схему при подключении автоматизации.
"""
from __future__ import annotations

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.urls import reverse
from django.utils import timezone


class Role(models.TextChoices):
    ADMIN = "admin", "Администратор"
    HEAD = "head", "Руководитель"
    MANAGER = "manager", "Менеджер"


class User(AbstractUser):
    """Пользователь системы. Роль определяет доступ к данным."""

    role = models.CharField("Роль", max_length=16, choices=Role.choices, default=Role.MANAGER)
    phone = models.CharField("Телефон", max_length=32, blank=True)
    is_active_manager = models.BooleanField("Активен как менеджер", default=True)

    class Meta:
        verbose_name = "Пользователь"
        verbose_name_plural = "Пользователи"
        ordering = ["first_name", "last_name", "username"]

    def __str__(self) -> str:
        return self.get_full_name() or self.username

    @property
    def display_name(self) -> str:
        return self.get_full_name() or self.username

    @property
    def is_admin_role(self) -> bool:
        return self.role == Role.ADMIN or self.is_superuser

    @property
    def is_head_role(self) -> bool:
        return self.role == Role.HEAD

    @property
    def can_see_all_clients(self) -> bool:
        return self.is_admin_role or self.is_head_role

    @property
    def can_manage_settings(self) -> bool:
        return self.is_admin_role


class Stage(models.Model):
    """Стадия воронки. Настраивается администратором."""

    name = models.CharField("Название", max_length=64, unique=True)
    slug = models.SlugField("Код", max_length=64, unique=True)
    order = models.PositiveIntegerField("Порядок", default=0)
    color = models.CharField("Цвет", max_length=16, default="#64748b")
    is_active = models.BooleanField("Активна", default=True)
    in_funnel = models.BooleanField("В основной воронке", default=True)
    is_won = models.BooleanField("Успешное завершение (сделка)", default=False)
    is_lost = models.BooleanField("Проигрыш", default=False)

    class Meta:
        verbose_name = "Стадия"
        verbose_name_plural = "Стадии"
        ordering = ["order", "id"]

    def __str__(self) -> str:
        return self.name


class Funnel(models.Model):
    """Воронка/проект (напр. «Эл Насип», «Standart House») — к чему относится лид.

    Не путать с ``Stage.in_funnel`` (это флаг «в основной воронке стадий»)."""

    name = models.CharField("Название", max_length=100, unique=True)
    slug = models.SlugField("Код", max_length=100, unique=True)
    order = models.PositiveIntegerField("Порядок", default=0)
    is_active = models.BooleanField("Активна", default=True)

    class Meta:
        verbose_name = "Воронка"
        verbose_name_plural = "Воронки"
        ordering = ["order", "id"]

    def __str__(self) -> str:
        return self.name


class Client(models.Model):
    """Клиент. Основной идентификатор для дедупликации — нормализованный телефон."""

    class Source(models.TextChoices):
        UNKNOWN = "unknown", "Не указан"
        BITRIX = "bitrix", "База Bitrix"
        MANUAL = "manual", "Вручную"
        EXCEL = "excel", "Импорт Excel"
        WHATSAPP = "whatsapp", "WhatsApp"
        CALL = "call", "Звонок"
        INSTAGRAM = "instagram", "Instagram"
        REFERRAL = "referral", "Рекомендация"
        SITE = "site", "Сайт"
        OTHER = "other", "Другое"

    full_name = models.CharField("ФИО", max_length=255)
    last_name = models.CharField("Фамилия", max_length=100, blank=True)
    first_name = models.CharField("Имя", max_length=100, blank=True)
    middle_name = models.CharField("Отчество", max_length=100, blank=True)
    phone = models.CharField("Телефон", max_length=32, blank=True)
    phone_normalized = models.CharField("Телефон (норм.)", max_length=32, blank=True, db_index=True)
    phone_extra = models.CharField("Доп. телефон", max_length=32, blank=True)
    whatsapp_phone = models.CharField("WhatsApp", max_length=32, blank=True)

    first_contact_date = models.DateField("Дата обращения", null=True, blank=True)
    manager = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Менеджер",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="clients",
    )
    source = models.CharField("Источник", max_length=16, choices=Source.choices, default=Source.UNKNOWN)
    stage = models.ForeignKey(Stage, verbose_name="Стадия", on_delete=models.PROTECT, related_name="clients")
    funnel = models.ForeignKey(
        Funnel, verbose_name="Воронка", on_delete=models.SET_NULL, null=True, blank=True, related_name="clients"
    )

    looking_for = models.TextField("Что ищет", blank=True)
    what_has = models.TextField("Что есть", blank=True)
    budget = models.CharField("Бюджет", max_length=255, blank=True)
    comment = models.TextField("Комментарий", blank=True)
    lost_reason = models.CharField("Причина проигрыша", max_length=255, blank=True)

    # Приходят из выгрузок Bitrix24 при импорте — своей логики их не трогает.
    last_contact_at = models.DateTimeField("Дата последней коммуникации", null=True, blank=True)
    last_activity_at = models.DateTimeField("Последняя активность", null=True, blank=True)

    next_step = models.CharField("Следующий шаг", max_length=255, blank=True)
    next_step_at = models.DateTimeField("Срок следующего действия", null=True, blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField("Создан", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлён", auto_now=True)

    class Meta:
        verbose_name = "Клиент"
        verbose_name_plural = "Клиенты"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["stage", "manager"]),
            models.Index(fields=["next_step_at"]),
        ]

    def __str__(self) -> str:
        return self.full_name

    def save(self, *args, **kwargs):
        # Если ФИО введено по частям (Фамилия/Имя/Отчество) — собираем строку для поиска и отображения.
        if self.last_name or self.first_name or self.middle_name:
            self.full_name = " ".join(
                p for p in (self.last_name, self.first_name, self.middle_name) if p
            ).strip() or self.full_name
        # Нормализованный телефон — единый внутренний формат для поиска (без +, пробелов, дефисов).
        from .utils import normalize_phone

        self.phone_normalized = normalize_phone(self.phone)
        update_fields = kwargs.get("update_fields")
        if update_fields is not None and "phone" in update_fields:
            kwargs["update_fields"] = list(update_fields) + ["phone_normalized"]
        super().save(*args, **kwargs)

    def get_absolute_url(self) -> str:
        return reverse("client_detail", args=[self.pk])

    @property
    def wa_number(self) -> str:
        from .utils import normalize_phone

        raw = self.whatsapp_phone or self.phone
        return normalize_phone(raw)

    @property
    def has_open_task(self) -> bool:
        return self.tasks.filter(status__in=[Task.Status.NEW, Task.Status.IN_PROGRESS]).exists()

    @property
    def next_task(self):
        return (
            self.tasks.filter(status__in=[Task.Status.NEW, Task.Status.IN_PROGRESS])
            .order_by("due_date", "due_time")
            .first()
        )


class ClientHistory(models.Model):
    """Лента истории взаимодействия с клиентом."""

    class Kind(models.TextChoices):
        CREATED = "created", "Клиент создан"
        STAGE = "stage", "Смена стадии"
        TASK = "task", "Задача"
        COMMENT = "comment", "Комментарий"
        MESSAGE = "message", "Сообщение"
        WHATSAPP = "whatsapp", "WhatsApp"
        MANAGER = "manager", "Смена менеджера"
        IMPORT = "import", "Импорт"
        FIELD = "field", "Изменение данных"

    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="history")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    kind = models.CharField(max_length=16, choices=Kind.choices)
    text = models.CharField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Событие истории"
        verbose_name_plural = "История клиента"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.get_kind_display()}: {self.text}"


class Comment(models.Model):
    """Комментарий в карточке клиента."""

    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    text = models.TextField("Текст")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Комментарий"
        verbose_name_plural = "Комментарии"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.text[:60]


class Task(models.Model):
    """Задача менеджера, всегда связана с клиентом."""

    class Status(models.TextChoices):
        NEW = "new", "Новая"
        IN_PROGRESS = "in_progress", "В работе"
        DONE = "done", "Выполнена"
        OVERDUE = "overdue", "Просрочена"

    title = models.CharField("Название", max_length=255)
    client = models.ForeignKey(Client, verbose_name="Клиент", on_delete=models.CASCADE, related_name="tasks")
    manager = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="Менеджер", on_delete=models.SET_NULL, null=True, related_name="tasks"
    )
    due_date = models.DateField("Дата", null=True, blank=True)
    due_time = models.TimeField("Время", null=True, blank=True)
    comment = models.TextField("Комментарий", blank=True)
    status = models.CharField("Статус", max_length=16, choices=Status.choices, default=Status.NEW)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Задача"
        verbose_name_plural = "Задачи"
        ordering = ["due_date", "due_time", "-created_at"]

    def __str__(self) -> str:
        return self.title

    def get_absolute_url(self) -> str:
        return reverse("task_detail", args=[self.pk])

    @property
    def is_open(self) -> bool:
        return self.status in {self.Status.NEW, self.Status.IN_PROGRESS}

    @property
    def is_overdue(self) -> bool:
        if not self.is_open or not self.due_date:
            return False
        now = timezone.localtime()
        if self.due_date < now.date():
            return True
        if self.due_date == now.date() and self.due_time and self.due_time < now.time():
            return True
        return False

    @property
    def due_human(self) -> str:
        """Короткая подпись срока: «Просрочено», «Сегодня», «Завтра» или дата."""
        if not self.due_date:
            return "без срока"
        today = timezone.localdate()
        delta = (self.due_date - today).days
        if self.is_overdue:
            return "Просрочено"
        if delta == 0:
            return "Сегодня"
        if delta == 1:
            return "Завтра"
        return self.due_date.strftime("%d.%m")

    @property
    def due_tone(self) -> str:
        """red / amber / green — для окраски чипа."""
        if self.is_overdue:
            return "red"
        if self.due_date and (self.due_date - timezone.localdate()).days <= 1:
            return "amber"
        return "green"


class MessageTemplate(models.Model):
    """Шаблон сообщения с переменными вида {имя}, {телефон}, {менеджер}, {объект}."""

    name = models.CharField("Название", max_length=255)
    body = models.TextField("Текст")
    is_active = models.BooleanField("Активен", default=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Шаблон сообщения"
        verbose_name_plural = "Шаблоны сообщений"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Message(models.Model):
    """Подготовленное для клиента сообщение.

    Статус не переводится в «отправлено» автоматически — только вручную
    менеджером, т.к. CRM технически не видит факт отправки в WhatsApp.
    """

    class Status(models.TextChoices):
        PREPARED = "prepared", "Подготовлено"
        OPENED = "opened", "Открыто в WhatsApp"
        SENT_MANUAL = "sent_manual", "Отправлено вручную"
        SKIPPED = "skipped", "Пропущено"

    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="messages")
    template = models.ForeignKey(MessageTemplate, on_delete=models.SET_NULL, null=True, blank=True)
    task = models.ForeignKey(Task, on_delete=models.SET_NULL, null=True, blank=True, related_name="messages")
    manager = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    rendered_text = models.TextField("Итоговый текст")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PREPARED)
    batch = models.ForeignKey(
        "BroadcastBatch", on_delete=models.SET_NULL, null=True, blank=True, related_name="messages"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    opened_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Сообщение"
        verbose_name_plural = "Сообщения"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.client} — {self.get_status_display()}"


class WhatsAppAction(models.Model):
    """Факт открытия WhatsApp с подготовленным текстом (для аналитики этапа 2)."""

    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="whatsapp_actions")
    message = models.ForeignKey(Message, on_delete=models.SET_NULL, null=True, blank=True)
    manager = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    phone = models.CharField(max_length=32)
    text = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Открытие WhatsApp"
        verbose_name_plural = "Открытия WhatsApp"
        ordering = ["-created_at"]


class BroadcastBatch(models.Model):
    """Ручная массовая рассылка: набор подготовленных сообщений, которые
    менеджер по очереди открывает в WhatsApp и отправляет вручную."""

    template = models.ForeignKey(MessageTemplate, on_delete=models.SET_NULL, null=True)
    manager = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Массовая рассылка"
        verbose_name_plural = "Массовые рассылки"
        ordering = ["-created_at"]

    @property
    def total(self) -> int:
        return self.messages.count()

    @property
    def done(self) -> int:
        return self.messages.exclude(status=Message.Status.PREPARED).count()


class Notification(models.Model):
    class Kind(models.TextChoices):
        TASK_NEW = "task_new", "Новая задача"
        TASK_TODAY = "task_today", "Задача на сегодня"
        TASK_OVERDUE = "task_overdue", "Просроченная задача"
        CLIENT_NEW = "client_new", "Новый клиент"
        CLIENT_ASSIGNED = "client_assigned", "Клиент назначен"
        STAGE_CHANGED = "stage_changed", "Изменение стадии"
        COMMENT = "comment", "Комментарий"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    text = models.CharField(max_length=300)
    url = models.CharField(max_length=300, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Уведомление"
        verbose_name_plural = "Уведомления"
        ordering = ["-created_at"]


class ImportLog(models.Model):
    """Журнал импорта Excel. Защищает от повторного импорта того же файла."""

    class Status(models.TextChoices):
        DONE = "done", "Завершён"
        FAILED = "failed", "Ошибка"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    filename = models.CharField(max_length=255)
    file_hash = models.CharField(max_length=64, blank=True, db_index=True)
    mapping = models.JSONField(default=dict)
    total_rows = models.PositiveIntegerField(default=0)
    created_count = models.PositiveIntegerField(default=0)
    updated_count = models.PositiveIntegerField(default=0)
    skipped_count = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DONE)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Импорт"
        verbose_name_plural = "Импорты"
        ordering = ["-created_at"]
