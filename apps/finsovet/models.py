"""Модели «Финсовета» — плоская таблица вопросов, как в Excel/CRM.

Главный объект — ВОПРОС (Question). У него есть статус, действие, срок и
ответственный — редактируются прямо в строке. История (кто что сказал и что
изменилось) копится сама в Entry — ничего не нужно переносить вручную.
«Задачи» и «Сегодня» — это не отдельные таблицы, а фильтры/срезы тех же
вопросов (см. views.py).
"""
from __future__ import annotations

from django.conf import settings
from django.db import models
from django.urls import reverse


class Block(models.Model):
    """Блок/раздел, к которому относится вопрос: К Блок, ЖЗИ, Финансы и т.д."""

    name = models.CharField("Название", max_length=100)
    slug = models.SlugField("Slug", max_length=100, unique=True)
    order = models.PositiveSmallIntegerField("Порядок", default=0)
    color = models.CharField("Цвет", max_length=7, default="#8e8e93", help_text="HEX, например #1b8a4c")
    is_active = models.BooleanField("Активен", default=True)

    class Meta:
        ordering = ["order", "name"]
        verbose_name = "Блок"
        verbose_name_plural = "Блоки"

    def __str__(self) -> str:
        return self.name

    @property
    def text_color(self) -> str:
        """Чёрный текст на светлом фоне (бежевый, жёлтый), белый — на тёмном."""
        hex_c = (self.color or "#8e8e93").lstrip("#")
        if len(hex_c) != 6:
            return "#fff"
        r, g, b = (int(hex_c[i:i + 2], 16) for i in (0, 2, 4))
        luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
        return "#1c1c1e" if luminance > 0.6 else "#fff"


class Question(models.Model):
    """Один вопрос — одна строка в таблице. Вокруг него крутится всё остальное."""

    class Status(models.TextChoices):
        SOON = "soon", "Скоро"
        IN_PROGRESS = "in_progress", "В процессе"
        DONE = "done", "Завершён"
        FROZEN = "frozen", "Заморожен"

    block = models.ForeignKey(Block, on_delete=models.PROTECT, related_name="questions", verbose_name="Блок")
    order = models.IntegerField("Порядок", default=0)
    title = models.CharField("Вопрос", max_length=300)
    status = models.CharField("Статус", max_length=16, choices=Status.choices, default=Status.SOON)
    action = models.CharField("Действие", max_length=200, blank=True, default="")
    due_date = models.DateField("Срок", null=True, blank=True)
    responsible = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="finsovet_questions", verbose_name="Ответственный",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField("Активен", default=True)

    class Meta:
        ordering = ["order", "-updated_at"]
        verbose_name = "Вопрос"
        verbose_name_plural = "Вопросы"
        indexes = [models.Index(fields=["block", "status"])]

    def __str__(self) -> str:
        return f"{self.block} — {self.title}"

    def get_absolute_url(self) -> str:
        return reverse("finsovet:question_detail", args=[self.pk])

    @property
    def has_action(self) -> bool:
        return bool(self.action)

    @property
    def is_overdue(self) -> bool:
        from django.utils import timezone

        return bool(self.due_date) and self.status != self.Status.DONE and self.due_date < timezone.localdate()

    @property
    def due_tone(self) -> str:
        from datetime import timedelta

        from django.utils import timezone

        if not self.due_date or self.status == self.Status.DONE:
            return ""
        if self.is_overdue:
            return "red"
        if self.due_date <= timezone.localdate() + timedelta(days=2):
            return "amber"
        return ""

    @property
    def last_comment(self):
        return self.entries.filter(kind=Entry.Kind.COMMENT).order_by("-created_at").first()

    def recent_entries(self, limit=5):
        return self.entries.select_related("author").order_by("-created_at")[:limit]


class Entry(models.Model):
    """История вопроса: комментарий пользователя или автоматическая запись об изменении поля."""

    class Kind(models.TextChoices):
        COMMENT = "comment", "Комментарий"
        CHANGE = "change", "Изменение"

    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="entries", verbose_name="Вопрос")
    kind = models.CharField("Тип", max_length=16, choices=Kind.choices, default=Kind.COMMENT)
    text = models.TextField("Текст")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="finsovet_entries", verbose_name="Автор",
    )
    created_at = models.DateTimeField("Дата", auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Запись"
        verbose_name_plural = "Записи"

    def __str__(self) -> str:
        return f"{self.question} — {self.text[:40]}"


class DebtNote(models.Model):
    """Заметка по текущим долгам — доска в духе Apple Notes / Google Keep:
    любой с доступом к Финсовету может добавить, отредактировать или убрать
    любую карточку (совместная работа, без персонального владения)."""

    COLORS = ["#fff8c5", "#d8f0d3", "#d6e9fb", "#ffe1d1", "#ead6fb", "#f0f0f0"]

    text = models.TextField("Текст", blank=True, default="")
    color = models.CharField("Цвет", max_length=7, default=COLORS[0])
    order = models.IntegerField("Порядок", default=0)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["order", "-updated_at"]
        verbose_name = "Заметка о долге"
        verbose_name_plural = "Заметки о долгах"

    def __str__(self) -> str:
        return self.text[:60] or f"Заметка #{self.pk}"


# --------------------------------------------------------------------------- #
#  Панель «Финансы»: план выплат (65%) и ожидаемые средства (35%).
#  Таблицы правятся как в Excel — каждая ячейка сохраняется сама.
# --------------------------------------------------------------------------- #
class Payment(models.Model):
    """Строка «плана выплат»: кому и сколько нужно заплатить. «Оплачено» не хранится,
    а складывается из выплат (PaymentRecord) — так у каждой строки есть история."""

    order = models.IntegerField("Порядок", default=0)
    due = models.CharField("Дата выплаты / срок", max_length=100, blank=True, default="")
    name = models.CharField("Наименование", max_length=300, blank=True, default="")
    total = models.DecimalField("Общая сумма долга", max_digits=14, decimal_places=2, default=0)
    extra = models.CharField("Дополнительно", max_length=300, blank=True, default="")
    notes = models.CharField("Примечание", max_length=500, blank=True, default="")
    is_active = models.BooleanField("Активна", default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["order", "id"]
        verbose_name = "Выплата (план)"
        verbose_name_plural = "План выплат"

    def __str__(self) -> str:
        return self.name or f"Выплата #{self.pk}"

    @property
    def paid(self):
        # используем аннотацию из вьюхи, если она есть — без лишнего запроса на строку
        if hasattr(self, "paid_sum"):
            return self.paid_sum or 0
        return self.records.aggregate(s=models.Sum("amount"))["s"] or 0

    @property
    def remaining(self):
        return self.total - self.paid

    @property
    def is_done(self) -> bool:
        """Завершена — долг есть и выплачен полностью (показывается зачёркнутой)."""
        return self.total > 0 and self.remaining <= 0


class PaymentRecord(models.Model):
    """Одна фактическая выплата по строке плана — из них строится история с датами."""

    payment = models.ForeignKey(Payment, on_delete=models.CASCADE, related_name="records", verbose_name="Строка плана")
    amount = models.DecimalField("Сумма", max_digits=14, decimal_places=2)
    date = models.DateField("Дата выплаты")
    note = models.CharField("Комментарий", max_length=300, blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-created_at"]
        verbose_name = "Выплата"
        verbose_name_plural = "Выплаты"

    def __str__(self) -> str:
        return f"{self.payment} — {self.amount} ({self.date:%d.%m.%Y})"


class ExpectedFund(models.Model):
    """Строка «ожидаемых средств»: откуда и когда придут деньги."""

    order = models.IntegerField("Порядок", default=0)
    source = models.CharField("Источник", max_length=300, blank=True, default="")
    amount = models.DecimalField("Сумма", max_digits=14, decimal_places=2, default=0)
    due = models.CharField("Срок", max_length=100, blank=True, default="")
    notes = models.CharField("Примечание", max_length=500, blank=True, default="")
    is_active = models.BooleanField("Активна", default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["order", "id"]
        verbose_name = "Ожидаемые средства"
        verbose_name_plural = "Ожидаемые средства"

    def __str__(self) -> str:
        return self.source or f"Поступление #{self.pk}"
