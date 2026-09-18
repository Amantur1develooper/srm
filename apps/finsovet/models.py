"""Модели «Финсовета» — рабочей панели финансового совета.

Главный принцип: ничего не перезаписывается. Любое изменение — это новая
запись (Entry) в журнале узла; «текущее состояние» — это просто последняя
такая запись. Старые записи никуда не удаляются — они и есть история.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone


class Section(models.Model):
    """Раздел верхнего уровня: Финансы / Продажи / Производство и т.д."""

    name = models.CharField("Название", max_length=100)
    slug = models.SlugField("Slug", max_length=100, unique=True)
    order = models.PositiveSmallIntegerField("Порядок", default=0)
    is_active = models.BooleanField("Активен", default=True)

    class Meta:
        ordering = ["order", "name"]
        verbose_name = "Раздел"
        verbose_name_plural = "Разделы"

    def __str__(self) -> str:
        return self.name


class Node(models.Model):
    """Универсальный узел дерева: объект / блок / работа / этап.

    Уровни не типизированы жёстко — просто дерево произвольной глубины.
    Корневые узлы (parent=None) — «объекты», они отображаются как заголовок
    группы. У любого узла может быть и своё состояние, и дочерние узлы.
    """

    section = models.ForeignKey(Section, on_delete=models.CASCADE, related_name="nodes", verbose_name="Раздел")
    parent = models.ForeignKey(
        "self", on_delete=models.CASCADE, null=True, blank=True, related_name="children", verbose_name="Родитель"
    )
    name = models.CharField("Название", max_length=200)
    order = models.PositiveSmallIntegerField("Порядок", default=0)
    is_active = models.BooleanField("Активен", default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["order", "name"]
        verbose_name = "Узел"
        verbose_name_plural = "Узлы"
        indexes = [models.Index(fields=["section", "parent"])]

    def __str__(self) -> str:
        return self.name

    def get_absolute_url(self) -> str:
        return reverse("finsovet:node_detail", args=[self.pk])

    @property
    def is_root(self) -> bool:
        return self.parent_id is None

    @property
    def path(self) -> str:
        """«Ала-Тоо → Лифт» — для форм и поиска."""
        parts = [self.name]
        p = self.parent
        while p:
            parts.append(p.name)
            p = p.parent
        return " → ".join(reversed(parts))

    @property
    def current_entry(self):
        """Последняя запись, отражающая состояние узла (в т.ч. проблема)."""
        return self.entries.filter(kind__in=[Entry.Kind.STATE, Entry.Kind.PROBLEM]).order_by("-created_at").first()

    @property
    def current_state_text(self) -> str:
        e = self.current_entry
        return e.text if e else ""

    @property
    def has_open_problem(self) -> bool:
        e = self.current_entry
        return bool(e and e.kind == Entry.Kind.PROBLEM)

    @property
    def open_task(self):
        return self.tasks.exclude(status=Task.Status.DONE).order_by("due_date", "-created_at").first()

    def recent_entries(self, limit=5):
        return self.entries.select_related("author").order_by("-created_at")[:limit]

    def descendant_ids(self):
        """Себя и все дочерние узлы (любой глубины) — для объединённой ленты «чата» объекта."""
        if getattr(self, "_descendant_ids_cache", None) is None:
            ids = [self.id]
            for child in self.children.filter(is_active=True):
                ids.extend(child.descendant_ids())
            self._descendant_ids_cache = ids
        return self._descendant_ids_cache

    def feed_entries(self):
        """Лента объекта: все записи по нему и по всем его работам, от старых к новым — как переписка."""
        return Entry.objects.filter(node_id__in=self.descendant_ids()).select_related("node", "author").order_by("created_at")

    def feed_tasks(self):
        return Task.objects.filter(node_id__in=self.descendant_ids()).select_related("node", "assignee")

    @property
    def last_activity(self):
        return self.entries.model.objects.filter(node_id__in=self.descendant_ids()).select_related("node", "author").order_by("-created_at").first()

    @property
    def open_tasks_count(self) -> int:
        return self.feed_tasks().exclude(status=Task.Status.DONE).count()

    @property
    def open_problems(self):
        return [n for n in Node.objects.filter(id__in=self.descendant_ids()) if n.has_open_problem]

    @property
    def open_problems_count(self) -> int:
        return len(self.open_problems)


class Entry(models.Model):
    """Запись в журнале узла: состояние, комментарий или проблема."""

    class Kind(models.TextChoices):
        STATE = "state", "Состояние"
        COMMENT = "comment", "Комментарий"
        PROBLEM = "problem", "Проблема"

    node = models.ForeignKey(Node, on_delete=models.CASCADE, related_name="entries", verbose_name="Узел")
    kind = models.CharField("Тип", max_length=16, choices=Kind.choices, default=Kind.STATE)
    text = models.TextField("Текст")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="finsovet_entries", verbose_name="Кто сообщил",
    )
    created_at = models.DateTimeField("Дата", auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Запись"
        verbose_name_plural = "Записи"

    def __str__(self) -> str:
        return f"{self.node} — {self.get_kind_display()}: {self.text[:40]}"


class Task(models.Model):
    class Status(models.TextChoices):
        NEW = "new", "Новая"
        IN_PROGRESS = "in_progress", "В работе"
        DONE = "done", "Готово"
        BLOCKED = "blocked", "Заблокирована"

    node = models.ForeignKey(
        Node, on_delete=models.CASCADE, null=True, blank=True, related_name="tasks", verbose_name="Узел"
    )
    section = models.ForeignKey(
        Section, on_delete=models.SET_NULL, null=True, blank=True, related_name="tasks", verbose_name="Раздел"
    )
    title = models.CharField("Что сделать", max_length=300)
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="finsovet_tasks", verbose_name="Кто",
    )
    due_date = models.DateField("Когда", null=True, blank=True)
    status = models.CharField("Статус", max_length=16, choices=Status.choices, default=Status.NEW)
    comment = models.TextField("Комментарий", blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+", verbose_name="Создал",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["status", "due_date", "-created_at"]
        verbose_name = "Задача"
        verbose_name_plural = "Задачи"

    def __str__(self) -> str:
        return self.title

    def get_absolute_url(self) -> str:
        return reverse("finsovet:task_detail", args=[self.pk])

    @property
    def is_open(self) -> bool:
        return self.status != self.Status.DONE

    @property
    def is_overdue(self) -> bool:
        return self.is_open and bool(self.due_date) and self.due_date < timezone.localdate()

    @property
    def due_human(self) -> str:
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
        if self.is_overdue:
            return "red"
        if self.due_date and (self.due_date - timezone.localdate()).days <= 1:
            return "amber"
        return "green"


class TaskEvent(models.Model):
    """История задачи: смена срока/статуса — так же не перезаписывается, а копится."""

    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="events")
    text = models.CharField(max_length=300)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "История задачи"
        verbose_name_plural = "История задач"

    def __str__(self) -> str:
        return self.text


class Decision(models.Model):
    """Решение Финсовета — отдельно от задачи, но может её породить."""

    section = models.ForeignKey(
        Section, on_delete=models.SET_NULL, null=True, blank=True, related_name="decisions", verbose_name="Раздел"
    )
    node = models.ForeignKey(
        Node, on_delete=models.SET_NULL, null=True, blank=True, related_name="decisions", verbose_name="Узел"
    )
    text = models.TextField("Решение")
    responsible = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="finsovet_decisions", verbose_name="Ответственный",
    )
    due_date = models.DateField("Срок", null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+", verbose_name="Автор",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Решение"
        verbose_name_plural = "Решения"

    def __str__(self) -> str:
        return self.text[:60]


class Meeting(models.Model):
    """Отметка о проведённом заседании — граница для «что изменилось» и протокола."""

    date = models.DateField("Дата заседания", default=timezone.localdate)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField("Заметки", blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Заседание"
        verbose_name_plural = "Заседания"

    def __str__(self) -> str:
        return f"Заседание {self.date:%d.%m.%Y}"

    def get_absolute_url(self) -> str:
        return reverse("finsovet:protocol_detail", args=[self.pk])
