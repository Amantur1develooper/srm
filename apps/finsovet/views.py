from __future__ import annotations

from django.contrib import messages as flash
from django.db.models import Q
from django.http import HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .access import finsovet_required, responsible_people
from .forms import BlockForm, CommentForm, QuestionQuickForm
from .models import Block, Entry, Question
from .utils import log_change, log_entry

STATUS_LABELS = dict(Question.Status.choices)


def _back(request, fallback):
    return request.META.get("HTTP_REFERER") or fallback


def _base_ctx():
    return {"blocks": Block.objects.filter(is_active=True), "people": responsible_people(), "statuses": Question.Status.choices}


@finsovet_required
def dashboard(request):
    """Главный экран: одна строка = один вопрос, всё редактируется на месте."""
    q = request.GET.get("q", "").strip()
    block_slug = request.GET.get("block", "")
    status = request.GET.get("status", "")

    qs = Question.objects.filter(is_active=True).select_related("block", "responsible")
    if q:
        qs = qs.filter(
            Q(title__icontains=q) | Q(action__icontains=q) | Q(entries__text__icontains=q)
        ).distinct()
    if block_slug:
        qs = qs.filter(block__slug=block_slug)
    if status:
        qs = qs.filter(status=status)

    ctx = {
        **_base_ctx(),
        "questions": qs,
        "q": q,
        "block_slug": block_slug,
        "status": status,
        "quick_form": QuestionQuickForm(),
        "total": Question.objects.filter(is_active=True).count(),
    }
    return render(request, "finsovet/dashboard.html", ctx)


@finsovet_required
@require_POST
def question_add(request):
    """«+ Добавить»: блок + вопрос обязательны, остальное можно позже."""
    form = QuestionQuickForm(request.POST)
    if form.is_valid():
        question = form.save(commit=False)
        question.created_by = request.user
        question.save()
        flash.success(request, f"Добавлено: {question.title}")
        return redirect(_back(request, reverse("finsovet:dashboard")))
    flash.error(request, "Проверьте поля — блок и вопрос обязательны")
    return redirect(_back(request, reverse("finsovet:dashboard")))


@finsovet_required
def question_detail(request, pk):
    question = get_object_or_404(Question.objects.select_related("block", "responsible"), pk=pk)
    ctx = {
        **_base_ctx(),
        "question": question,
        "entries": question.entries.select_related("author").order_by("-created_at")[:200],
        "comment_form": CommentForm(),
    }
    return render(request, "finsovet/question_detail.html", ctx)


QUESTION_INLINE_FIELDS = {"title", "status", "action", "due_date", "responsible"}


@finsovet_required
@require_POST
def question_inline_update(request, pk):
    """Правка прямо в строке: клик → изменить → сохранить. Любое изменение уходит в историю."""
    question = get_object_or_404(Question, pk=pk)
    field = request.POST.get("field", "")
    value = request.POST.get("value", "").strip()
    if field not in QUESTION_INLINE_FIELDS:
        return HttpResponseBadRequest("bad field")

    if field == "title":
        if not value:
            return JsonResponse({"ok": False, "error": "Вопрос не может быть пустым"}, status=400)
        old = question.title
        if old == value:
            return JsonResponse({"ok": True, "changed": False})
        question.title = value
        question.save(update_fields=["title", "updated_at"])
        log_change(question, f"Вопрос изменён: «{old}» → «{value}»", request.user)
        return JsonResponse({"ok": True, "label": value, "changed": True})

    if field == "status":
        if value not in Question.Status.values:
            return JsonResponse({"ok": False, "error": "Неверный статус"}, status=400)
        old = question.get_status_display()
        if question.status == value:
            return JsonResponse({"ok": True, "changed": False})
        question.status = value
        question.save(update_fields=["status", "updated_at"])
        log_change(question, f"Статус: {old} → {question.get_status_display()}", request.user)
        return JsonResponse({"ok": True, "label": question.get_status_display(), "changed": True})

    if field == "action":
        old = question.action
        if old == value:
            return JsonResponse({"ok": True, "changed": False})
        question.action = value
        question.save(update_fields=["action", "updated_at"])
        log_change(question, f"Действие: {old or '—'} → {value or '—'}", request.user)
        return JsonResponse({"ok": True, "label": value or "—", "changed": True})

    if field == "due_date":
        old = question.due_date
        if not value:
            question.due_date = None
        else:
            try:
                question.due_date = timezone.datetime.strptime(value, "%Y-%m-%d").date()
            except ValueError:
                return JsonResponse({"ok": False, "error": "Неверная дата"}, status=400)
        if old == question.due_date:
            return JsonResponse({"ok": True, "changed": False})
        question.save(update_fields=["due_date", "updated_at"])
        log_change(
            question,
            f"Срок: {old.strftime('%d.%m.%Y') if old else '—'} → {question.due_date.strftime('%d.%m.%Y') if question.due_date else '—'}",
            request.user,
        )
        return JsonResponse({
            "ok": True, "changed": True,
            "label": question.due_date.strftime("%d.%m.%Y") if question.due_date else "—",
            "overdue": question.is_overdue,
        })

    if field == "responsible":
        old = question.responsible
        obj = responsible_people().filter(pk=value).first() if value else None
        if old == obj:
            return JsonResponse({"ok": True, "changed": False})
        question.responsible = obj
        question.save(update_fields=["responsible", "updated_at"])
        log_change(question, f"Ответственный: {old or '—'} → {obj or '—'}", request.user)
        return JsonResponse({"ok": True, "label": str(obj) if obj else "—", "changed": True})

    return HttpResponseBadRequest("bad field")


@finsovet_required
@require_POST
def question_comment_add(request, pk):
    """Пользователь пишет только текст — дата, время и автор проставляются сами."""
    question = get_object_or_404(Question, pk=pk)
    form = CommentForm(request.POST)
    if form.is_valid():
        log_entry(question, Entry.Kind.COMMENT, form.cleaned_data["text"], request.user)
        question.save(update_fields=["updated_at"])
        flash.success(request, "Комментарий добавлен")
    else:
        flash.error(request, "Проверьте текст комментария")
    return redirect(_back(request, question.get_absolute_url()))


@finsovet_required
def task_list(request):
    """«Задачи» — не отдельная таблица, а те же вопросы, где заполнено «Действие»."""
    person_id = request.GET.get("responsible", "")
    qs = (
        Question.objects.filter(is_active=True)
        .exclude(action="")
        .exclude(status=Question.Status.DONE)
        .select_related("block", "responsible")
        .order_by("due_date", "block__order")
    )
    if person_id:
        qs = qs.filter(responsible_id=person_id)
    ctx = {**_base_ctx(), "questions": qs, "person_id": person_id}
    return render(request, "finsovet/task_list.html", ctx)


@finsovet_required
def today_view(request):
    """«Сегодня» — что изменилось сегодня, без отдельного протокола/дневника."""
    today = timezone.localdate()
    entries = (
        Entry.objects.filter(created_at__date=today)
        .select_related("question", "question__block", "author")
        .order_by("question__block__order", "-created_at")
    )
    ctx = {**_base_ctx(), "entries": entries, "today": today}
    return render(request, "finsovet/today.html", ctx)


@finsovet_required
def structure(request):
    """Список блоков — можно расширять."""
    if request.method == "POST":
        form = BlockForm(request.POST)
        if form.is_valid():
            form.save()
            flash.success(request, "Блок добавлен")
            return redirect("finsovet:structure")
        flash.error(request, "Проверьте поля")
    ctx = {"all_blocks": Block.objects.all(), "block_form": BlockForm()}
    return render(request, "finsovet/structure.html", ctx)
