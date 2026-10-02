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
    is_active = models.BooleanField("Активен", default=True)

    class Meta:
        ordering = ["order", "name"]
        verbose_name = "Блок"
        verbose_name_plural = "Блоки"

    def __str__(self) -> str:
        return self.name


class Question(models.Model):
    """Один вопрос — одна строка в таблице. Вокруг него крутится всё остальное."""

    class Status(models.TextChoices):
        SOON = "soon", "Скоро"
        IN_PROGRESS = "in_progress", "В процессе"
        DONE = "done", "Завершён"
        FROZEN = "frozen", "Заморожен"

    block = models.ForeignKey(Block, on_delete=models.PROTECT, related_name="questions", verbose_name="Блок")
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
        ordering = ["block__order", "-updated_at"]
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
