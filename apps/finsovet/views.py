from __future__ import annotations

from django.contrib import messages as flash
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.http import HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .access import finsovet_members, finsovet_required
from .forms import CommentForm, DecisionForm, NodeForm, QuickEntryForm, SectionForm, StateUpdateForm, TaskQuickForm
from .models import Decision, Entry, Meeting, Node, Section, Task, TaskEvent
from .utils import log_entry, log_task_event

User = get_user_model()


def _back(request, fallback):
    return request.META.get("HTTP_REFERER") or fallback


def _flatten(node, depth=0):
    """Дерево -> плоский список (узел, глубина) для отрисовки списком с отступами."""
    rows = []
    for child in node.children.filter(is_active=True).order_by("order", "name"):
        rows.append((child, depth))
        rows.extend(_flatten(child, depth + 1))
    return rows


@finsovet_required
def dashboard(request):
    """Главный экран — простой список: Раздел → Объект → строки (как Excel, без обучения).
    Клик по названию узла открывает его «переписку» — полную историю и чат (node_detail)."""
    q = request.GET.get("q", "").strip()
    sections = Section.objects.filter(is_active=True)
    base_ctx = {"members": finsovet_members(), "quick_form": QuickEntryForm()}

    if q:
        matched = (
            Node.objects.filter(is_active=True)
            .filter(Q(name__icontains=q) | Q(entries__text__icontains=q) | Q(tasks__title__icontains=q))
            .select_related("section", "parent", "parent__parent")
            .distinct()
        )
        groups = []
        for section in sections:
            rows = [n for n in matched if n.section_id == section.id]
            if rows:
                groups.append({"section": section, "objects": [{"root": None, "rows": [(n, 0) for n in rows]}]})
        return render(request, "finsovet/dashboard.html", {**base_ctx, "groups": groups, "q": q, "search_mode": True})

    groups = []
    for section in sections:
        roots = Node.objects.filter(section=section, parent=None, is_active=True).order_by("order", "name")
        objects = []
        for root in roots:
            objects.append({"root": root, "rows": _flatten(root)})
        if objects:
            groups.append({"section": section, "objects": objects})
    return render(request, "finsovet/dashboard.html", {**base_ctx, "groups": groups, "q": "", "search_mode": False})


@finsovet_required
@require_POST
def object_message_add(request):
    """Строка ввода внизу «переписки» узла — свободное сообщение по нему или по конкретной работе внутри."""
    node = get_object_or_404(Node, pk=request.POST.get("node_id"))
    text = request.POST.get("text", "").strip()
    if text:
        kind = Entry.Kind.PROBLEM if request.POST.get("is_problem") == "1" else Entry.Kind.COMMENT
        log_entry(node, kind, text, request.user)
    return redirect(_back(request, node.get_absolute_url()))


@finsovet_required
def node_detail(request, pk):
    """Карточка узла — история/переписка по нему и всем его работам, задачи, решения. Открывается кликом со списка."""
    node = get_object_or_404(Node.objects.select_related("section", "parent"), pk=pk)
    feed_items = []
    for e in node.feed_entries():
        feed_items.append({"kind": "entry", "at": e.created_at, "entry": e})
    for t in node.feed_tasks():
        feed_items.append({"kind": "task", "at": t.created_at, "task": t})
    feed_items.sort(key=lambda x: x["at"])
    ctx = {
        "node": node,
        "feed_items": feed_items,
        "works": node.children.filter(is_active=True).order_by("order", "name"),
        "open_tasks": node.feed_tasks().exclude(status=Task.Status.DONE).order_by("due_date"),
        "open_problems": node.open_problems,
        "decisions": Decision.objects.filter(node_id__in=node.descendant_ids()).select_related("responsible")[:20],
        "task_form": TaskQuickForm(),
        "decision_form": DecisionForm(),
        "members": finsovet_members(),
    }
    return render(request, "finsovet/node_detail.html", ctx)


@finsovet_required
@require_POST
def entry_add(request):
    """«+ ДОБАВИТЬ»: куда / что произошло / кто сообщил."""
    form = QuickEntryForm(request.POST)
    if form.is_valid():
        node = form.cleaned_data["node"]
        author = form.cleaned_data["reported_by"] or request.user
        log_entry(node, Entry.Kind.STATE, form.cleaned_data["text"], author)
        flash.success(request, f"Добавлено: {node.path}")
        return redirect(_back(request, reverse("finsovet:dashboard")))
    flash.error(request, "Проверьте поля")
    return redirect(_back(request, reverse("finsovet:dashboard")))


@finsovet_required
@require_POST
def node_state_update(request, pk):
    node = get_object_or_404(Node, pk=pk)
    form = StateUpdateForm(request.POST)
    if form.is_valid():
        author = form.cleaned_data["reported_by"] or request.user
        kind = Entry.Kind.PROBLEM if form.cleaned_data["is_problem"] else Entry.Kind.STATE
        log_entry(node, kind, form.cleaned_data["text"], author)
        flash.success(request, "Состояние обновлено")
    else:
        flash.error(request, "Проверьте поле")
    return redirect(_back(request, node.get_absolute_url()))


@finsovet_required
@require_POST
def node_comment_add(request, pk):
    node = get_object_or_404(Node, pk=pk)
    form = CommentForm(request.POST)
    if form.is_valid():
        author = form.cleaned_data["reported_by"] or request.user
        log_entry(node, Entry.Kind.COMMENT, form.cleaned_data["text"], author)
        flash.success(request, "Комментарий добавлен")
    else:
        flash.error(request, "Проверьте поле")
    return redirect(_back(request, node.get_absolute_url()))


@finsovet_required
@require_POST
def node_task_add(request, pk):
    node = get_object_or_404(Node, pk=pk)
    form = TaskQuickForm(request.POST)
    if form.is_valid():
        t = form.save(commit=False)
        t.node = node
        t.section = node.section
        t.created_by = request.user
        t.save()
        flash.success(request, "Задача создана")
    else:
        flash.error(request, "Проверьте поля задачи")
    return redirect(_back(request, node.get_absolute_url()))


@finsovet_required
@require_POST
def task_add(request):
    """Задача без привязки к узлу — из вкладки «Задачи»."""
    form = TaskQuickForm(request.POST)
    if form.is_valid():
        t = form.save(commit=False)
        t.created_by = request.user
        t.save()
        flash.success(request, "Задача создана")
    else:
        flash.error(request, "Проверьте поля задачи")
    return redirect(_back(request, reverse("finsovet:task_list")))


@finsovet_required
def task_list(request):
    qs = Task.objects.select_related("node", "node__section", "assignee")
    assignee_id = request.GET.get("assignee", "")
    status = request.GET.get("status", "open")
    if assignee_id:
        qs = qs.filter(assignee_id=assignee_id)
    if status == "open":
        qs = qs.exclude(status=Task.Status.DONE)
    elif status in Task.Status.values:
        qs = qs.filter(status=status)
    ctx = {
        "tasks": qs,
        "members": finsovet_members(),
        "assignee_id": assignee_id,
        "status": status,
        "form": TaskQuickForm(),
    }
    return render(request, "finsovet/task_list.html", ctx)


@finsovet_required
def task_detail(request, pk):
    task = get_object_or_404(Task.objects.select_related("node", "assignee"), pk=pk)
    ctx = {"task": task, "events": task.events.select_related("author")[:100]}
    return render(request, "finsovet/task_detail.html", ctx)


@finsovet_required
@require_POST
def task_status(request, pk):
    task = get_object_or_404(Task, pk=pk)
    status = request.POST.get("status", "")
    if status not in Task.Status.values:
        return HttpResponseBadRequest("bad status")
    old = task.get_status_display()
    task.status = status
    task.completed_at = timezone.now() if status == Task.Status.DONE else None
    task.save(update_fields=["status", "completed_at", "updated_at"])
    log_task_event(task, f"Статус: {old} → {task.get_status_display()}", request.user)
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({"ok": True, "status": task.get_status_display(), "done": status == Task.Status.DONE})
    flash.success(request, "Статус обновлён")
    return redirect(_back(request, task.get_absolute_url()))


TASK_INLINE_FIELDS = {"title", "due_date"}


@finsovet_required
@require_POST
def task_inline_update(request, pk):
    task = get_object_or_404(Task, pk=pk)
    field = request.POST.get("field", "")
    value = request.POST.get("value", "").strip()
    if field not in TASK_INLINE_FIELDS:
        return HttpResponseBadRequest("bad field")
    if field == "title" and not value:
        return JsonResponse({"ok": False, "error": "Название не может быть пустым"}, status=400)
    old = getattr(task, field)
    if field == "due_date":
        if not value:
            task.due_date = None
        else:
            try:
                task.due_date = timezone.datetime.strptime(value, "%Y-%m-%d").date()
            except ValueError:
                return JsonResponse({"ok": False, "error": "Неверная дата"}, status=400)
    else:
        task.title = value
    task.save(update_fields=[field, "updated_at"])
    if str(old or "") != value:
        label = "Срок" if field == "due_date" else "Название"
        log_task_event(task, f"{label} изменён: {old or '—'} → {value or '—'}", request.user)
    return JsonResponse({"ok": True, "value": value, "due_human": task.due_human, "due_tone": task.due_tone})


@finsovet_required
def decisions_list(request):
    ctx = {
        "decisions": Decision.objects.select_related("section", "node", "responsible"),
        "form": DecisionForm(),
        "nodes": Node.objects.filter(is_active=True).select_related("parent", "parent__parent"),
    }
    return render(request, "finsovet/decisions_list.html", ctx)


@finsovet_required
@require_POST
def decision_add(request):
    form = DecisionForm(request.POST)
    if form.is_valid():
        d = form.save(commit=False)
        node_id = request.POST.get("node_id", "")
        if node_id:
            node = Node.objects.filter(pk=node_id).first()
            if node:
                d.node = node
                d.section = node.section
        d.created_by = request.user
        d.save()
        flash.success(request, "Решение записано")
    else:
        flash.error(request, "Проверьте поля решения")
    return redirect(_back(request, reverse("finsovet:decisions_list")))


def _last_meeting():
    return Meeting.objects.order_by("-created_at").first()


def _changes_since(since):
    entries = Entry.objects.select_related("node", "node__section", "author").order_by("-created_at")
    tasks = Task.objects.select_related("node", "node__section", "assignee").order_by("-created_at")
    decisions = Decision.objects.select_related("section", "node", "responsible").order_by("-created_at")
    if since is not None:
        entries = entries.filter(created_at__gt=since)
        tasks = tasks.filter(created_at__gt=since)
        decisions = decisions.filter(created_at__gt=since)
    return entries, tasks, decisions


@finsovet_required
def changes_view(request):
    last = _last_meeting()
    since = last.created_at if last else None
    entries, tasks, decisions = _changes_since(since)
    state_entries = entries.filter(kind__in=[Entry.Kind.STATE, Entry.Kind.PROBLEM])
    ctx = {
        "last_meeting": last,
        "state_entries": state_entries,
        "tasks": tasks,
        "decisions": decisions,
        "has_changes": state_entries.exists() or tasks.exists() or decisions.exists(),
    }
    return render(request, "finsovet/changes.html", ctx)


@finsovet_required
def protocol_list(request):
    return render(request, "finsovet/protocol_list.html", {"meetings": Meeting.objects.select_related("created_by")})


@finsovet_required
@require_POST
def protocol_generate(request):
    meeting = Meeting.objects.create(created_by=request.user)
    flash.success(request, "Протокол сформирован")
    return redirect("finsovet:protocol_detail", pk=meeting.pk)


@finsovet_required
def protocol_detail(request, pk):
    meeting = get_object_or_404(Meeting, pk=pk)
    prev = Meeting.objects.filter(created_at__lt=meeting.created_at).order_by("-created_at").first()
    since = prev.created_at if prev else None
    entries = Entry.objects.select_related("node", "node__section").filter(
        created_at__gt=since, created_at__lte=meeting.created_at
    ) if since else Entry.objects.select_related("node", "node__section").filter(created_at__lte=meeting.created_at)
    tasks = Task.objects.select_related("node", "assignee").filter(
        created_at__gt=since, created_at__lte=meeting.created_at
    ) if since else Task.objects.select_related("node", "assignee").filter(created_at__lte=meeting.created_at)
    decisions = Decision.objects.select_related("section", "node", "responsible").filter(
        created_at__gt=since, created_at__lte=meeting.created_at
    ) if since else Decision.objects.select_related("section", "node", "responsible").filter(created_at__lte=meeting.created_at)
    open_problems = Node.objects.filter(is_active=True).select_related("section")
    open_problems = [n for n in open_problems if n.has_open_problem]
    ctx = {
        "meeting": meeting,
        "prev_meeting": prev,
        "state_entries": entries.filter(kind__in=[Entry.Kind.STATE, Entry.Kind.PROBLEM]).order_by("-created_at"),
        "tasks": tasks.order_by("-created_at"),
        "decisions": decisions.order_by("-created_at"),
        "open_problems": open_problems,
    }
    return render(request, "finsovet/protocol_detail.html", ctx)


@finsovet_required
def structure(request):
    if request.method == "POST":
        form_kind = request.POST.get("form_kind")
        if form_kind == "section":
            sform = SectionForm(request.POST)
            if sform.is_valid():
                sform.save()
                flash.success(request, "Раздел добавлен")
                return redirect("finsovet:structure")
        else:
            nform = NodeForm(request.POST)
            if nform.is_valid():
                nform.save()
                flash.success(request, "Узел добавлен")
                return redirect("finsovet:structure")
        flash.error(request, "Проверьте поля")
    ctx = {
        "sections": Section.objects.all(),
        "nodes": Node.objects.filter(is_active=True).select_related("section", "parent"),
        "section_form": SectionForm(),
        "node_form": NodeForm(),
    }
    return render(request, "finsovet/structure.html", ctx)


@finsovet_required
@require_POST
def node_deactivate(request, pk):
    node = get_object_or_404(Node, pk=pk)
    node.is_active = False
    node.save(update_fields=["is_active"])
    flash.success(request, f"«{node.name}» скрыт")
    return redirect(_back(request, reverse("finsovet:structure")))
