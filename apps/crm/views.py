from __future__ import annotations

import json
import uuid
from pathlib import Path
from urllib.parse import quote

from django.conf import settings
from django.contrib import messages as flash
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Prefetch, Q
from django.http import (
    Http404,
    HttpResponse,
    HttpResponseBadRequest,
    HttpResponseRedirect,
    JsonResponse,
)
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .access import (
    clients_for,
    ensure_client_access,
    ensure_settings,
    messages_for,
    tasks_for,
)
from .forms import (
    ClientForm,
    CommentForm,
    ImportUploadForm,
    MessageTemplateForm,
    QuickTaskForm,
    StageForm,
    TaskForm,
    UserForm,
)
from .models import (
    BroadcastBatch,
    Client,
    ClientHistory,
    Funnel,
    Message,
    MessageTemplate,
    Notification,
    Stage,
    Task,
    WhatsAppAction,
)
from .services import excel_export, excel_import
from .utils import log_history, notify, render_template

User = get_user_model()

IMPORT_DIR = Path(settings.MEDIA_ROOT) / "imports"


# --------------------------------------------------------------------------- #
#  Dashboard
# --------------------------------------------------------------------------- #
# «Главное» показывает только текущую рабочую воронку — без «Сделка» и «Проигранные»,
# чтобы старые закрытые лиды не перегружали основной экран.
DASHBOARD_STAGE_SLUGS = ["new", "accepted", "consult", "hot", "cold", "frozen"]


@login_required
def dashboard(request):
    """Главное: акцент на новых лидах и текущей работе — не на всей базе."""
    user = request.user
    clients = clients_for(user)
    tasks = tasks_for(user)
    today = timezone.localdate()

    dash_stages = list(
        Stage.objects.filter(slug__in=DASHBOARD_STAGE_SLUGS, is_active=True).order_by("order")
    )
    stage_slug = request.GET.get("stage", "new")
    if stage_slug not in DASHBOARD_STAGE_SLUGS:
        stage_slug = "new"

    open_tasks_qs = Task.objects.filter(
        status__in=[Task.Status.NEW, Task.Status.IN_PROGRESS]
    ).order_by("due_date", "due_time")
    feed_qs = (
        clients.filter(stage__slug=stage_slug)
        .select_related("stage", "manager")
        .prefetch_related(Prefetch("tasks", queryset=open_tasks_qs, to_attr="open_tasks"))
        .order_by("-created_at")
    )

    open_tasks = tasks.filter(status__in=[Task.Status.NEW, Task.Status.IN_PROGRESS])

    ctx = {
        "dash_stages": dash_stages,
        "dash_counts": {s.slug: clients.filter(stage=s).count() for s in dash_stages},
        "stage_slug": stage_slug,
        "feed": feed_qs[:30],
        "feed_total": feed_qs.count(),
        "stages": Stage.objects.filter(is_active=True),  # для смены стадии прямо в строке
        "clients_total": clients.count(),
        "tasks_today": open_tasks.filter(due_date=today).count(),
        "tasks_overdue": open_tasks.filter(due_date__lt=today).count(),
        "my_tasks": open_tasks.select_related("client").order_by("due_date", "due_time")[:6],
    }
    return render(request, "crm/dashboard.html", ctx)


# --------------------------------------------------------------------------- #
#  Клиенты
# --------------------------------------------------------------------------- #
@login_required
def client_list(request):
    user = request.user
    qs = clients_for(user)
    qs = _apply_client_filters(request, qs, user)

    sort = request.GET.get("sort", "-created_at")
    allowed_sort = {
        "full_name", "-full_name", "created_at", "-created_at",
        "next_step_at", "-next_step_at", "stage__order", "-stage__order",
    }
    if sort in allowed_sort:
        qs = qs.order_by(sort)

    open_tasks_qs = Task.objects.filter(
        status__in=[Task.Status.NEW, Task.Status.IN_PROGRESS]
    ).order_by("due_date", "due_time")
    qs = qs.prefetch_related(Prefetch("tasks", queryset=open_tasks_qs, to_attr="open_tasks"))

    paginator = Paginator(qs, 40)
    page = paginator.get_page(request.GET.get("page"))

    ctx = {
        "page_obj": page,
        "total": paginator.count,
        "stages": Stage.objects.filter(is_active=True),
        "managers": User.objects.filter(is_active=True, role="manager").order_by("first_name", "username"),
        "funnels": Funnel.objects.filter(is_active=True),
        "sources": Client.Source.choices,
        "templates": MessageTemplate.objects.filter(is_active=True),
        "current": request.GET,
        "sort": sort,
        "querystring": _querystring(request, exclude=["page"]),
        "qs_no_stage": _querystring(request, exclude=["page", "stage"]),
        "qs_no_manager": _querystring(request, exclude=["page", "manager"]),
        "qs_no_funnel": _querystring(request, exclude=["page", "funnel"]),
        "qs_no_source": _querystring(request, exclude=["page", "source"]),
        "stage_counts": dict(_client_counts_by(clients_for(user), "stage__slug")),
        "manager_counts": dict(_client_counts_by(clients_for(user), "manager_id")),
        "funnel_counts": dict(_client_counts_by(clients_for(user), "funnel__slug")),
        "source_counts": dict(_client_counts_by(clients_for(user), "source")),
    }
    return render(request, "crm/client_list.html", ctx)


def _client_counts_by(qs, field):
    return list(qs.values(field).annotate(n=Count("id")).values_list(field, "n"))


def _apply_client_filters(request, qs, user):
    g = request.GET
    q = g.get("q", "").strip()
    if q:
        qs = qs.filter(
            Q(full_name__icontains=q)
            | Q(phone__icontains=q)
            | Q(phone_normalized__icontains=q)
            | Q(looking_for__icontains=q)
            | Q(comment__icontains=q)
        )
    if g.get("stage"):
        qs = qs.filter(stage__slug=g["stage"])
    if g.get("manager"):
        qs = qs.filter(manager_id=g["manager"])
    if g.get("source"):
        qs = qs.filter(source=g["source"])
    if g.get("funnel"):
        qs = qs.filter(funnel__slug=g["funnel"])
    if g.get("date_from"):
        qs = qs.filter(first_contact_date__gte=g["date_from"])
    if g.get("date_to"):
        qs = qs.filter(first_contact_date__lte=g["date_to"])
    if g.get("created_from"):
        qs = qs.filter(created_at__date__gte=g["created_from"])
    if g.get("created_to"):
        qs = qs.filter(created_at__date__lte=g["created_to"])
    if g.get("has_phone") == "1":
        qs = qs.exclude(phone_normalized="")
    if g.get("has_task") == "1":
        qs = qs.filter(tasks__status__in=[Task.Status.NEW, Task.Status.IN_PROGRESS]).distinct()
    if g.get("overdue_task") == "1":
        qs = qs.filter(
            tasks__status__in=[Task.Status.NEW, Task.Status.IN_PROGRESS],
            tasks__due_date__lt=timezone.localdate(),
        ).distinct()
    if g.get("next_from"):
        qs = qs.filter(next_step_at__date__gte=g["next_from"])
    if g.get("next_to"):
        qs = qs.filter(next_step_at__date__lte=g["next_to"])
    return qs


def _querystring(request, exclude=None):
    exclude = set(exclude or [])
    parts = [f"{k}={quote(v)}" for k, v in request.GET.items() if k not in exclude and v]
    return "&".join(parts)


@login_required
def client_export(request):
    qs = _apply_client_filters(request, clients_for(request.user), request.user)
    data = excel_export.export_clients(qs)
    resp = HttpResponse(
        data,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    ts = timezone.localtime().strftime("%Y%m%d-%H%M")
    resp["Content-Disposition"] = f'attachment; filename="clients-{ts}.xlsx"'
    return resp


@login_required
@require_POST
def client_bulk_action(request):
    ids = request.POST.getlist("client_ids")
    action = request.POST.get("action")
    qs = clients_for(request.user).filter(id__in=ids)
    n = qs.count()
    if not n:
        flash.warning(request, "Не выбрано ни одного клиента")
        return redirect("client_list")

    if action == "set_manager":
        if not request.user.can_see_all_clients:
            flash.error(request, "Недостаточно прав")
            return redirect("client_list")
        mgr = get_object_or_404(User, pk=request.POST.get("manager"))
        for c in qs:
            if c.manager_id != mgr.id:
                log_history(c, ClientHistory.Kind.MANAGER, f"Менеджер: {mgr.display_name}", request.user)
                notify(mgr, Notification.Kind.CLIENT_ASSIGNED, f"Вам назначен клиент: {c.full_name}", c.get_absolute_url())
        qs.update(manager=mgr)
        flash.success(request, f"Менеджер изменён у {n} клиентов")
    elif action == "set_stage":
        stage = get_object_or_404(Stage, pk=request.POST.get("stage"))
        reason = request.POST.get("lost_reason", "")
        for c in qs:
            _do_stage_change(c, stage, request.user, lost_reason=reason)
        flash.success(request, f"Стадия изменена у {n} клиентов")
    elif action == "set_funnel":
        funnel = get_object_or_404(Funnel, pk=request.POST.get("funnel"))
        qs.update(funnel=funnel)
        flash.success(request, f"Воронка изменена у {n} клиентов")
    elif action == "set_source":
        source = request.POST.get("source")
        if source not in Client.Source.values:
            flash.error(request, "Неизвестный источник")
            return redirect("client_list")
        qs.update(source=source)
        flash.success(request, f"Источник изменён у {n} клиентов")
    elif action == "export":
        data = excel_export.export_clients(qs)
        resp = HttpResponse(
            data, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        resp["Content-Disposition"] = 'attachment; filename="clients-selected.xlsx"'
        return resp
    elif action == "broadcast":
        request.session["broadcast_ids"] = list(map(int, ids))
        return redirect("broadcast_start")
    elif action == "delete":
        deleted = n
        qs.delete()
        flash.success(request, f"Удалено: {deleted}")
        return redirect("client_list")  # реферер мог указывать на удалённого клиента
    else:
        flash.warning(request, "Неизвестное действие")
    return redirect(request.META.get("HTTP_REFERER", "client_list"))


@login_required
def client_detail(request, pk):
    client = get_object_or_404(clients_for(request.user), pk=pk)
    ensure_client_access(request.user, client)
    ctx = {
        "client": client,
        "history": client.history.select_related("user")[:100],
        "comments": client.comments.select_related("author"),
        "tasks": client.tasks.select_related("manager").order_by("status", "due_date"),
        "client_messages": client.messages.select_related("template").order_by("-created_at")[:20],
        "comment_form": CommentForm(),
        "task_form": QuickTaskForm(),
        "stages": Stage.objects.filter(is_active=True),
        "templates": MessageTemplate.objects.filter(is_active=True),
    }
    return render(request, "crm/client_detail.html", ctx)


@login_required
def client_create(request):
    form = ClientForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        client = form.save(commit=False)
        if not request.user.can_see_all_clients:
            client.manager = request.user
        client.created_by = request.user
        client.first_contact_date = timezone.localdate()  # дата фиксации — автоматически
        client.stage = Stage.objects.filter(slug="new", is_active=True).first() or Stage.objects.order_by("order").first()
        client.save()
        log_history(client, ClientHistory.Kind.CREATED, "Клиент создан", request.user)
        if client.manager and client.manager_id != request.user.id:
            notify(client.manager, Notification.Kind.CLIENT_ASSIGNED,
                   f"Вам назначен клиент: {client.full_name}", client.get_absolute_url())
        title = form.cleaned_data.get("task_title")
        if title:
            t = Task.objects.create(
                title=title, client=client, manager=client.manager or request.user,
                due_date=form.cleaned_data.get("task_date"), created_by=request.user,
            )
            log_history(client, ClientHistory.Kind.TASK, f"Задача: {t.title}", request.user)
        flash.success(request, "Клиент создан")
        return redirect(client)
    return render(request, "crm/client_form.html", {"form": form, "title": "Новая сделка"})


@login_required
def client_edit(request, pk):
    client = get_object_or_404(clients_for(request.user), pk=pk)
    ensure_client_access(request.user, client)
    old_manager = client.manager_id
    form = ClientForm(request.POST or None, instance=client, user=request.user)
    if request.method == "POST" and form.is_valid():
        obj = form.save()
        if obj.manager_id != old_manager:
            log_history(obj, ClientHistory.Kind.MANAGER,
                        f"Менеджер: {obj.manager.display_name if obj.manager else '—'}", request.user)
        flash.success(request, "Изменения сохранены")
        return redirect(obj)
    return render(request, "crm/client_form.html", {"form": form, "title": client.full_name, "client": client})


@login_required
@require_POST
def client_change_stage(request, pk):
    client = get_object_or_404(clients_for(request.user), pk=pk)
    ensure_client_access(request.user, client)
    stage = get_object_or_404(Stage, pk=request.POST.get("stage"))
    _do_stage_change(client, stage, request.user, lost_reason=request.POST.get("lost_reason", ""))
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({
            "ok": True,
            "stage": stage.name,
            "color": stage.color,
            "created_task": client.has_open_task,
        })
    flash.success(request, f"Стадия: {stage.name}")
    return redirect(request.META.get("HTTP_REFERER") or client.get_absolute_url())


def _do_stage_change(client, stage, user, lost_reason=""):
    if client.stage_id == stage.id:
        return
    old = client.stage.name
    client.stage = stage
    update_fields = ["stage", "updated_at"]
    if stage.is_lost and lost_reason:
        client.lost_reason = lost_reason[:255]
        update_fields.append("lost_reason")
    client.save(update_fields=update_fields)
    history_text = f"{old} → {stage.name}"
    if stage.is_lost and lost_reason:
        history_text += f" (причина: {lost_reason})"
    log_history(client, ClientHistory.Kind.STAGE, history_text, user)
    if client.manager_id:
        notify(client.manager, Notification.Kind.STAGE_CHANGED,
               f"{client.full_name}: {old} → {stage.name}", client.get_absolute_url())
    # Заготовка автоматизации этапа 2: при переходе в «Горячий» — создать задачу.
    if stage.slug == "hot" and not client.has_open_task:
        Task.objects.create(
            title="Связаться с клиентом",
            client=client,
            manager=client.manager,
            due_date=timezone.localdate(),
            created_by=user,
        )
        log_history(client, ClientHistory.Kind.TASK, "Автозадача: Связаться с клиентом", user)


@login_required
@require_POST
def client_add_comment(request, pk):
    client = get_object_or_404(clients_for(request.user), pk=pk)
    ensure_client_access(request.user, client)
    form = CommentForm(request.POST)
    if form.is_valid():
        c = form.save(commit=False)
        c.client = client
        c.author = request.user
        c.save()
        log_history(client, ClientHistory.Kind.COMMENT, c.text[:200], request.user)
        flash.success(request, "Комментарий добавлен")
    return redirect(client)


@login_required
@require_POST
def client_add_task(request, pk):
    client = get_object_or_404(clients_for(request.user), pk=pk)
    ensure_client_access(request.user, client)
    is_ajax = request.headers.get("x-requested-with") == "XMLHttpRequest"
    form = QuickTaskForm(request.POST)
    if form.is_valid():
        t = form.save(commit=False)
        t.client = client
        t.manager = client.manager or request.user
        t.created_by = request.user
        t.save()
        log_history(client, ClientHistory.Kind.TASK, f"Задача: {t.title}", request.user)
        notify(t.manager, Notification.Kind.TASK_NEW, f"Новая задача: {t.title} ({client.full_name})", t.get_absolute_url())
        if is_ajax:
            nxt = client.next_task
            return JsonResponse({
                "ok": True,
                "task": {"id": t.id, "title": t.title, "url": t.get_absolute_url()},
                "cell": {
                    "due": nxt.due_date.strftime("%d.%m") if nxt and nxt.due_date else "",
                    "overdue": bool(nxt and nxt.is_overdue),
                    "has_task": True,
                },
            })
        flash.success(request, "Задача создана")
    else:
        if is_ajax:
            return JsonResponse({"ok": False, "errors": form.errors}, status=400)
        flash.error(request, "Проверьте поля задачи")
    return redirect(request.META.get("HTTP_REFERER") or client.get_absolute_url())


@login_required
@require_POST
def client_bulk_task(request):
    """Создать одну и ту же задачу сразу нескольким выбранным клиентам."""
    is_ajax = request.headers.get("x-requested-with") == "XMLHttpRequest"
    ids = request.POST.getlist("client_ids")
    clients = list(clients_for(request.user).filter(id__in=ids))

    form = QuickTaskForm(request.POST)
    if not clients:
        msg = "Не выбрано ни одного клиента"
        if is_ajax:
            return JsonResponse({"ok": False, "error": msg}, status=400)
        flash.warning(request, msg)
        return redirect("client_list")
    if not form.is_valid():
        if is_ajax:
            return JsonResponse({"ok": False, "errors": form.errors}, status=400)
        flash.error(request, "Проверьте поля задачи")
        return redirect("client_list")

    cd = form.cleaned_data
    created = 0
    for client in clients:
        manager = client.manager or request.user
        t = Task.objects.create(
            title=cd["title"],
            client=client,
            manager=manager,
            due_date=cd.get("due_date"),
            due_time=cd.get("due_time"),
            comment=cd.get("comment", ""),
            created_by=request.user,
        )
        log_history(client, ClientHistory.Kind.TASK, f"Задача: {t.title}", request.user)
        if manager != request.user:
            notify(manager, Notification.Kind.TASK_NEW,
                   f"Новая задача: {t.title} ({client.full_name})", t.get_absolute_url())
        created += 1

    skipped = len(ids) - created
    msg = f"Задача «{cd['title']}» добавлена {created} клиент(ам)"
    if skipped:
        msg += f" (пропущено {skipped} — нет доступа)"
    if is_ajax:
        return JsonResponse({"ok": True, "created": created, "message": msg})
    flash.success(request, msg)
    return redirect(request.META.get("HTTP_REFERER") or "client_list")


@login_required
def client_whatsapp(request, pk):
    """Формирует текст, фиксирует действие и отправляет на wa.me с готовым текстом."""
    client = get_object_or_404(clients_for(request.user), pk=pk)
    ensure_client_access(request.user, client)

    number = client.wa_number
    if not number:
        flash.error(request, "У клиента не указан телефон")
        return redirect(client)

    template = None
    tpl_id = request.GET.get("template")
    text = request.GET.get("text", "")
    if tpl_id:
        template = MessageTemplate.objects.filter(pk=tpl_id).first()
    if template and not text:
        text = render_template(template.body, client)

    msg = Message.objects.create(
        client=client,
        template=template,
        manager=request.user,
        rendered_text=text,
        status=Message.Status.OPENED if text else Message.Status.OPENED,
        opened_at=timezone.now(),
    )
    WhatsAppAction.objects.create(
        client=client, message=msg, manager=request.user, phone=number, text=text
    )
    log_history(client, ClientHistory.Kind.WHATSAPP, "Открыт WhatsApp" + (" с сообщением" if text else ""), request.user)

    url = f"https://wa.me/{number}"
    if text:
        url += f"?text={quote(text)}"
    return HttpResponseRedirect(url)


# Поля, которые можно редактировать прямо на месте (клик → курсор → ввод), как в Excel.
INLINE_EDITABLE_FIELDS = {"full_name", "phone", "looking_for", "what_has", "comment"}


@login_required
@require_POST
def client_inline_update(request, pk):
    """Сохранить одно поле клиента без открытия карточки (Канбан/Список)."""
    client = get_object_or_404(clients_for(request.user), pk=pk)
    ensure_client_access(request.user, client)
    field = request.POST.get("field", "")
    value = request.POST.get("value", "").strip()
    if field not in INLINE_EDITABLE_FIELDS:
        return HttpResponseBadRequest("bad field")
    if field == "full_name" and not value:
        return JsonResponse({"ok": False, "error": "Имя не может быть пустым"}, status=400)
    old = getattr(client, field)
    if str(old or "") == value:
        return JsonResponse({"ok": True, "value": value, "changed": False})
    setattr(client, field, value)
    client.save(update_fields=[field, "updated_at"])
    labels = {"full_name": "ФИО", "phone": "Телефон", "looking_for": "Что ищет",
              "what_has": "Что есть", "comment": "Комментарий"}
    log_history(client, ClientHistory.Kind.FIELD, f"{labels.get(field, field)} изменено", request.user)
    return JsonResponse({"ok": True, "value": value, "changed": True})


@login_required
@require_POST
def client_quick_create(request):
    """Быстрое добавление заявки/сделки прямо из Канбана — минимум полей."""
    stage = get_object_or_404(Stage, pk=request.POST.get("stage"))
    full_name = request.POST.get("full_name", "").strip() or "Без имени"
    phone = request.POST.get("phone", "").strip()
    manager = request.user if not request.user.can_see_all_clients else None
    client = Client.objects.create(
        full_name=full_name, phone=phone, stage=stage, manager=manager,
        first_contact_date=timezone.localdate(), created_by=request.user,
    )
    log_history(client, ClientHistory.Kind.CREATED, "Быстро создан в Канбане", request.user)
    return JsonResponse({
        "ok": True,
        "client": {
            "id": client.id, "full_name": client.full_name, "phone": client.phone,
            "url": client.get_absolute_url(), "stage_id": stage.id,
        },
    })


# --------------------------------------------------------------------------- #
#  Канбан
# --------------------------------------------------------------------------- #
@login_required
def kanban(request):
    user = request.user
    qs = clients_for(user).select_related("manager", "stage")
    if request.GET.get("manager"):
        qs = qs.filter(manager_id=request.GET["manager"])
    if request.GET.get("q"):
        qs = qs.filter(full_name__icontains=request.GET["q"])

    stages = list(Stage.objects.filter(is_active=True, in_funnel=True).order_by("order"))
    extra = list(Stage.objects.filter(is_active=True, in_funnel=False).order_by("order"))
    all_stages = stages + extra

    by_stage = {s.id: [] for s in all_stages}
    for c in qs.order_by("-next_step_at", "-created_at")[:1000]:
        by_stage.setdefault(c.stage_id, []).append(c)

    columns = [{"stage": s, "clients": by_stage.get(s.id, [])} for s in all_stages]
    ctx = {
        "columns": columns,
        "stages": all_stages,
        "managers": User.objects.filter(is_active=True, role="manager").order_by("first_name"),
        "current": request.GET,
        "can_move": True,
    }
    return render(request, "crm/kanban.html", ctx)


@login_required
@require_POST
def kanban_move(request):
    try:
        payload = json.loads(request.body)
        client = clients_for(request.user).get(pk=payload["client_id"])
        stage = Stage.objects.get(pk=payload["stage_id"])
    except (KeyError, ValueError, Client.DoesNotExist, Stage.DoesNotExist):
        return HttpResponseBadRequest("bad request")
    ensure_client_access(request.user, client)
    _do_stage_change(client, stage, request.user, lost_reason=payload.get("lost_reason", ""))
    return JsonResponse({"ok": True, "stage": stage.name, "created_task": client.has_open_task})


# --------------------------------------------------------------------------- #
#  Задачи
# --------------------------------------------------------------------------- #
@login_required
def task_list(request):
    user = request.user
    qs = tasks_for(user)
    today = timezone.localdate()
    tab = request.GET.get("tab", "today")

    stage_slug = request.GET.get("stage", "")
    manager_id = request.GET.get("manager", "")
    if manager_id:
        qs = qs.filter(manager_id=manager_id)
    if stage_slug:
        qs = qs.filter(client__stage__slug=stage_slug)

    open_q = Q(status__in=[Task.Status.NEW, Task.Status.IN_PROGRESS])
    if tab == "today":
        view_qs = qs.filter(open_q, due_date=today)
    elif tab == "overdue":
        view_qs = qs.filter(open_q, due_date__lt=today)
    elif tab == "upcoming":
        view_qs = qs.filter(open_q, due_date__gt=today)
    elif tab == "no_date":
        view_qs = qs.filter(open_q, due_date__isnull=True)
    elif tab == "done":
        view_qs = qs.filter(status=Task.Status.DONE)
    else:
        view_qs = qs

    base = tasks_for(user)
    if manager_id:
        base = base.filter(manager_id=manager_id)
    if stage_slug:
        base = base.filter(client__stage__slug=stage_slug)
    counts = {
        "today": base.filter(open_q, due_date=today).count(),
        "overdue": base.filter(open_q, due_date__lt=today).count(),
        "upcoming": base.filter(open_q, due_date__gt=today).count(),
        "no_date": base.filter(open_q, due_date__isnull=True).count(),
        "done": base.filter(status=Task.Status.DONE).count(),
    }
    extra = []
    if stage_slug:
        extra.append(f"stage={quote(stage_slug)}")
    if manager_id:
        extra.append(f"manager={quote(manager_id)}")

    ctx = {
        "tasks": view_qs.select_related("client", "manager", "client__stage"),
        "tab": tab,
        "counts": counts,
        "managers": User.objects.filter(is_active=True, role="manager").order_by("first_name"),
        "stages": Stage.objects.filter(is_active=True),
        "current": request.GET,
        "filter_query": "&".join(extra),
        "has_filters": bool(extra),
    }
    return render(request, "crm/task_list.html", ctx)


@login_required
def task_create(request):
    client = None
    if request.GET.get("client"):
        client = clients_for(request.user).filter(pk=request.GET["client"]).first()
    form = TaskForm(request.POST or None, user=request.user, client=client)
    if request.method == "POST" and form.is_valid():
        t = form.save(commit=False)
        t.created_by = request.user
        if not t.manager:
            t.manager = t.client.manager or request.user
        t.save()
        log_history(t.client, ClientHistory.Kind.TASK, f"Задача: {t.title}", request.user)
        notify(t.manager, Notification.Kind.TASK_NEW, f"Новая задача: {t.title}", t.get_absolute_url())
        flash.success(request, "Задача создана")
        return redirect("task_detail", pk=t.pk)
    return render(request, "crm/task_form.html", {"form": form, "title": "Новая задача"})


@login_required
def task_detail(request, pk):
    task = get_object_or_404(tasks_for(request.user), pk=pk)
    ctx = {
        "task": task,
        "templates": MessageTemplate.objects.filter(is_active=True),
        "form": TaskForm(instance=task, user=request.user),
    }
    if request.method == "POST":
        form = TaskForm(request.POST, instance=task, user=request.user)
        if form.is_valid():
            form.save()
            flash.success(request, "Задача обновлена")
            return redirect("task_detail", pk=pk)
        ctx["form"] = form
    return render(request, "crm/task_detail.html", ctx)


@login_required
@require_POST
def task_set_status(request, pk):
    task = get_object_or_404(tasks_for(request.user), pk=pk)
    status = request.POST.get("status")
    if status not in Task.Status.values:
        return HttpResponseBadRequest("bad status")
    task.status = status
    if status == Task.Status.DONE:
        task.completed_at = timezone.now()
    task.save(update_fields=["status", "completed_at", "updated_at"])
    log_history(task.client, ClientHistory.Kind.TASK, f"Задача «{task.title}»: {task.get_status_display()}", request.user)
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({"ok": True, "status": task.get_status_display()})
    flash.success(request, "Статус обновлён")
    return redirect(request.META.get("HTTP_REFERER") or task.get_absolute_url())


TASK_INLINE_EDITABLE_FIELDS = {"title", "due_date", "due_time"}


@login_required
@require_POST
def task_inline_update(request, pk):
    """Правка задачи на месте в списке: клик → курсор → ввод (как в Excel)."""
    task = get_object_or_404(tasks_for(request.user), pk=pk)
    field = request.POST.get("field", "")
    value = request.POST.get("value", "").strip()
    if field not in TASK_INLINE_EDITABLE_FIELDS:
        return HttpResponseBadRequest("bad field")
    if field == "title" and not value:
        return JsonResponse({"ok": False, "error": "Название не может быть пустым"}, status=400)
    if field in {"due_date", "due_time"} and not value:
        setattr(task, field, None)
    elif field == "due_date":
        try:
            task.due_date = timezone.datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError:
            return JsonResponse({"ok": False, "error": "Неверная дата"}, status=400)
    elif field == "due_time":
        try:
            task.due_time = timezone.datetime.strptime(value, "%H:%M").time()
        except ValueError:
            return JsonResponse({"ok": False, "error": "Неверное время"}, status=400)
    else:
        setattr(task, field, value)
    task.save(update_fields=[field, "updated_at"])
    return JsonResponse({
        "ok": True,
        "due_human": task.due_human,
        "due_tone": task.due_tone,
        "is_overdue": task.is_overdue,
    })


@login_required
def task_make_message(request, pk):
    """Кнопка «Создать сообщение» в задаче: открывает редактор с подставленными данными."""
    task = get_object_or_404(tasks_for(request.user), pk=pk)
    client = task.client
    templates = MessageTemplate.objects.filter(is_active=True)
    tpl_id = request.GET.get("template") or request.POST.get("template")
    template = templates.filter(pk=tpl_id).first() if tpl_id else None

    if request.method == "POST":
        text = request.POST.get("text", "").strip()
        if not text:
            flash.error(request, "Текст сообщения пуст")
        else:
            msg = Message.objects.create(
                client=client, template=template, task=task, manager=request.user,
                rendered_text=text, status=Message.Status.PREPARED,
            )
            log_history(client, ClientHistory.Kind.MESSAGE, f"Сообщение из задачи «{task.title}»", request.user)
            number = client.wa_number
            if number:
                msg.status = Message.Status.OPENED
                msg.opened_at = timezone.now()
                msg.save(update_fields=["status", "opened_at"])
                WhatsAppAction.objects.create(
                    client=client, message=msg, manager=request.user, phone=number, text=text
                )
                return HttpResponseRedirect(f"https://wa.me/{number}?text={quote(text)}")
            flash.warning(request, "Сообщение подготовлено, но у клиента нет телефона для WhatsApp")
        return redirect("task_detail", pk=pk)

    initial_text = render_template(template.body, client) if template else ""
    ctx = {
        "task": task, "client": client, "templates": templates,
        "template": template, "initial_text": initial_text,
    }
    return render(request, "crm/message_editor.html", ctx)


# --------------------------------------------------------------------------- #
#  Сообщения и шаблоны
# --------------------------------------------------------------------------- #
@login_required
def message_list(request):
    qs = messages_for(request.user)
    if request.GET.get("status"):
        qs = qs.filter(status=request.GET["status"])
    paginator = Paginator(qs.select_related("client", "template", "manager"), 50)
    page = paginator.get_page(request.GET.get("page"))
    return render(request, "crm/message_list.html", {
        "page_obj": page, "statuses": Message.Status.choices, "current": request.GET,
    })


@login_required
@require_POST
def message_set_status(request, pk):
    msg = get_object_or_404(messages_for(request.user), pk=pk)
    status = request.POST.get("status")
    if status not in Message.Status.values:
        return HttpResponseBadRequest("bad status")
    msg.status = status
    if status == Message.Status.SENT_MANUAL:
        msg.sent_at = timezone.now()
    msg.save(update_fields=["status", "sent_at"])
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({"ok": True})
    flash.success(request, "Статус сообщения обновлён")
    return redirect(request.META.get("HTTP_REFERER") or "message_list")


@login_required
def template_list(request):
    return render(request, "crm/template_list.html", {
        "templates": MessageTemplate.objects.all(),
    })


@login_required
def template_create(request):
    form = MessageTemplateForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        obj.created_by = request.user
        obj.save()
        flash.success(request, "Шаблон создан")
        return redirect("template_list")
    return render(request, "crm/template_form.html", {"form": form, "title": "Новый шаблон"})


@login_required
def template_edit(request, pk):
    tpl = get_object_or_404(MessageTemplate, pk=pk)
    form = MessageTemplateForm(request.POST or None, instance=tpl)
    if request.method == "POST" and form.is_valid():
        form.save()
        flash.success(request, "Шаблон сохранён")
        return redirect("template_list")
    return render(request, "crm/template_form.html", {"form": form, "title": tpl.name})


@login_required
@require_POST
def template_delete(request, pk):
    tpl = get_object_or_404(MessageTemplate, pk=pk)
    tpl.delete()
    flash.success(request, "Шаблон удалён")
    return redirect("template_list")


# --------------------------------------------------------------------------- #
#  Массовая ручная рассылка
# --------------------------------------------------------------------------- #
@login_required
def broadcast_start(request):
    user = request.user
    ids = request.session.get("broadcast_ids", [])
    selected = clients_for(user).filter(id__in=ids) if ids else clients_for(user).none()

    if request.method == "POST":
        picked = request.POST.getlist("client_ids") or ids
        clients = list(clients_for(user).filter(id__in=picked))
        template = get_object_or_404(MessageTemplate, pk=request.POST.get("template"))
        if not clients:
            flash.error(request, "Не выбраны клиенты")
            return redirect("broadcast_start")
        batch = BroadcastBatch.objects.create(template=template, manager=user)
        for c in clients:
            Message.objects.create(
                client=c, template=template, manager=user, batch=batch,
                rendered_text=render_template(template.body, c),
                status=Message.Status.PREPARED,
            )
        request.session.pop("broadcast_ids", None)
        return redirect("broadcast_run", pk=batch.pk)

    ctx = {
        "selected": selected,
        "templates": MessageTemplate.objects.filter(is_active=True),
        "all_clients": clients_for(user).order_by("full_name") if not ids else None,
    }
    return render(request, "crm/broadcast_start.html", ctx)


@login_required
def broadcast_run(request, pk):
    batch = get_object_or_404(BroadcastBatch, pk=pk, manager=request.user)
    items = list(batch.messages.select_related("client").order_by("id"))
    items_json = [
        {
            "id": m.id,
            "name": m.client.full_name,
            "phone": m.client.wa_number,
            "text": m.rendered_text,
            "status": m.status,
        }
        for m in items
    ]
    ctx = {
        "batch": batch,
        "items": items,
        "items_json": items_json,
        "total": len(items),
    }
    return render(request, "crm/broadcast_run.html", ctx)


# --------------------------------------------------------------------------- #
#  Импорт Excel
# --------------------------------------------------------------------------- #
@login_required
def import_upload(request):
    ensure_settings_or_head(request.user)
    form = ImportUploadForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        f = form.cleaned_data["file"]
        raw = f.read()
        fhash = excel_import.file_hash(raw)
        from .models import ImportLog

        dup = ImportLog.objects.filter(file_hash=fhash, status=ImportLog.Status.DONE).first()

        prev = request.session.pop("import", None)
        if prev:
            (IMPORT_DIR / f"{prev['token']}.xlsx").unlink(missing_ok=True)

        IMPORT_DIR.mkdir(parents=True, exist_ok=True)
        token = uuid.uuid4().hex
        path = IMPORT_DIR / f"{token}.xlsx"
        path.write_bytes(raw)

        previews = excel_import.preview_workbook(raw)
        request.session["import"] = {
            "token": token,
            "filename": f.name,
            "sheets": [
                {
                    "name": p.sheet_name,
                    "headers": p.headers,
                    "header_row": p.header_row,
                    "total": p.total_rows,
                    "rows": [[str(x) for x in r] for r in p.rows],
                    "mapping": p.suggested_mapping,
                }
                for p in previews
            ],
        }
        if dup:
            flash.warning(request, f"Похоже, этот файл уже импортировали {dup.created_at:%d.%m.%Y %H:%M}. Проверьте перед повтором.")
        return redirect("import_map")
    return render(request, "crm/import_upload.html", {"form": form})


def ensure_settings_or_head(user):
    if not (user.can_manage_settings or user.is_head_role):
        from django.core.exceptions import PermissionDenied

        raise PermissionDenied("Импорт доступен администратору или руководителю")


@login_required
def import_map(request):
    ensure_settings_or_head(request.user)
    data = request.session.get("import")
    if not data:
        flash.error(request, "Сначала загрузите файл")
        return redirect("import_upload")

    sheet_idx = int(request.GET.get("sheet", 0))
    sheet_idx = max(0, min(sheet_idx, len(data["sheets"]) - 1))
    sheet = data["sheets"][sheet_idx]

    ctx = {
        "data": data,
        "sheet": sheet,
        "sheet_idx": sheet_idx,
        "target_fields": excel_import.TARGET_FIELDS,
        "managers": User.objects.filter(is_active=True, role="manager").order_by("first_name"),
        "columns": list(enumerate(sheet["headers"])),
    }
    return render(request, "crm/import_map.html", ctx)


@login_required
@require_POST
def import_run(request):
    ensure_settings_or_head(request.user)
    data = request.session.get("import")
    if not data:
        return redirect("import_upload")

    sheet_idx = int(request.POST.get("sheet", 0))
    sheet = data["sheets"][sheet_idx]
    path = IMPORT_DIR / f"{data['token']}.xlsx"
    if not path.exists():
        flash.error(request, "Файл импорта не найден, загрузите заново")
        return redirect("import_upload")

    mapping = {}
    for field_key, _label in excel_import.TARGET_FIELDS:
        val = request.POST.get(f"map_{field_key}", "")
        if val not in ("", "-"):
            mapping[field_key] = int(val)

    if "full_name" not in mapping and "phone" not in mapping:
        flash.error(request, "Нужно сопоставить хотя бы «ФИО» или «Телефон»")
        return redirect("import_map")

    default_manager = None
    if request.POST.get("default_manager"):
        default_manager = User.objects.filter(pk=request.POST["default_manager"]).first()

    strategy = request.POST.get("duplicate_strategy", "skip")
    result = excel_import.run_import(
        file_bytes=path.read_bytes(),
        filename=data["filename"],
        sheet_name=sheet["name"],
        header_row=sheet["header_row"],
        mapping=mapping,
        duplicate_strategy=strategy,
        default_manager=default_manager,
        user=request.user,
    )

    # Файл и сессию сохраняем — можно вернуться и повторить с другим сопоставлением.
    for e in result.errors:
        flash.error(request, e)

    ctx = {
        "result": result,
        "filename": data["filename"],
        "strategy": strategy,
        "strategy_label": {
            "skip": "пропустить дубли", "update": "обновить дубли", "create": "создавать новых",
        }.get(strategy, strategy),
        "name_mapped": "full_name" in mapping,
        "sheet_idx": sheet_idx,
    }
    return render(request, "crm/import_result.html", ctx)


@login_required
def import_finish(request):
    """Завершить импорт: убрать временный файл и данные из сессии."""
    data = request.session.pop("import", None)
    if data:
        (IMPORT_DIR / f"{data['token']}.xlsx").unlink(missing_ok=True)
    return redirect("client_list")


# --------------------------------------------------------------------------- #
#  Поиск, уведомления
# --------------------------------------------------------------------------- #
@login_required
def global_search(request):
    q = request.GET.get("q", "").strip()
    clients = tasks = []
    if q:
        clients = clients_for(request.user).filter(
            Q(full_name__icontains=q)
            | Q(phone__icontains=q)
            | Q(phone_normalized__icontains=q)
            | Q(looking_for__icontains=q)
            | Q(comment__icontains=q)
            | Q(stage__name__icontains=q)
            | Q(manager__first_name__icontains=q)
        )[:50]
        tasks = tasks_for(request.user).filter(title__icontains=q)[:20]
    return render(request, "crm/search.html", {"q": q, "clients": clients, "tasks": tasks})


@login_required
def notifications(request):
    qs = Notification.objects.filter(user=request.user)
    return render(request, "crm/notifications.html", {"items": qs[:100]})


@login_required
@require_POST
def notifications_read_all(request):
    Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
    return redirect(request.META.get("HTTP_REFERER") or "notifications")


# --------------------------------------------------------------------------- #
#  Администрирование
# --------------------------------------------------------------------------- #
@login_required
def admin_users(request):
    ensure_settings(request.user)
    users = User.objects.annotate(
        clients_count=Count("clients", distinct=True),
        tasks_count=Count("tasks", distinct=True),
    ).order_by("role", "first_name")
    return render(request, "crm/admin_users.html", {"users": users})


@login_required
def admin_user_create(request):
    ensure_settings(request.user)
    form = UserForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        flash.success(request, "Пользователь создан")
        return redirect("admin_users")
    return render(request, "crm/admin_user_form.html", {"form": form, "title": "Новый пользователь"})


@login_required
def admin_user_edit(request, pk):
    ensure_settings(request.user)
    obj = get_object_or_404(User, pk=pk)
    form = UserForm(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        form.save()
        flash.success(request, "Сохранено")
        return redirect("admin_users")
    return render(request, "crm/admin_user_form.html", {"form": form, "title": obj.display_name})


@login_required
def admin_stages(request):
    ensure_settings(request.user)
    if request.method == "POST":
        form = StageForm(request.POST)
        if form.is_valid():
            form.save()
            flash.success(request, "Стадия добавлена")
            return redirect("admin_stages")
    else:
        form = StageForm()
    return render(request, "crm/admin_stages.html", {
        "stages": Stage.objects.all(), "form": form,
    })
