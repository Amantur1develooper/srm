from __future__ import annotations

import random
import re

from django.contrib import messages as flash
from django.contrib.auth import get_user_model
from django.db.models import F, Q
from django.http import HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .access import finsovet_required, responsible_people
from .forms import BlockForm, BlockQuickForm, CommentForm, QuestionQuickForm, ResponsibleQuickForm
from .models import Block, DebtNote, Entry, Question
from .utils import log_change, log_entry

User = get_user_model()
STATUS_LABELS = dict(Question.Status.choices)


def _back(request, fallback):
    return request.META.get("HTTP_REFERER") or fallback


def _is_xhr(request):
    return request.headers.get("x-requested-with") == "XMLHttpRequest"


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

    # «Ответственные»: строка (имя, счётчик) и под ней топ-3 открытых задачи.
    people_panel = []
    for p in responsible_people():
        open_qs = (
            Question.objects.filter(is_active=True, responsible=p)
            .exclude(action="").exclude(status=Question.Status.DONE)
        )
        top = open_qs.select_related("block").order_by(F("due_date").asc(nulls_last=True), "order")[:3]
        overdue = open_qs.filter(due_date__lt=timezone.localdate()).count()
        people_panel.append({"person": p, "count": open_qs.count(), "overdue": overdue, "tasks": list(top)})

    ctx = {
        **_base_ctx(),
        "questions": qs,
        "q": q,
        "block_slug": block_slug,
        "status": status,
        "quick_form": QuestionQuickForm(),
        "block_quick_form": BlockQuickForm(),
        "responsible_quick_form": ResponsibleQuickForm(),
        "total": Question.objects.filter(is_active=True).count(),
        "people_panel": people_panel,
        "debt_notes": DebtNote.objects.select_related("updated_by", "created_by"),
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
        top = Question.objects.order_by("-order").values_list("order", flat=True).first() or 0
        question.order = top + 1
        question.save()
        if _is_xhr(request):
            return JsonResponse({"ok": True, "id": question.id, "title": question.title})
        flash.success(request, f"Добавлено: {question.title}")
        return redirect(_back(request, reverse("finsovet:dashboard")))
    if _is_xhr(request):
        return JsonResponse({"ok": False, "errors": form.errors}, status=400)
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
        if _is_xhr(request):
            return JsonResponse({"ok": True})
        flash.success(request, "Комментарий добавлен")
    else:
        if _is_xhr(request):
            return JsonResponse({"ok": False, "errors": form.errors}, status=400)
        flash.error(request, "Проверьте текст комментария")
    return redirect(_back(request, question.get_absolute_url()))


@finsovet_required
@require_POST
def question_delete(request, pk):
    """Удалить строку. Вопрос не стирается физически (история остаётся в базе),
    а просто перестаёт показываться — можно восстановить через админку."""
    question = get_object_or_404(Question, pk=pk)
    question.is_active = False
    question.save(update_fields=["is_active"])
    if _is_xhr(request):
        return JsonResponse({"ok": True})
    flash.success(request, f"«{question.title}» удалён")
    return redirect(_back(request, reverse("finsovet:dashboard")))


@finsovet_required
@require_POST
def question_reorder(request):
    """Перетаскивание строк — по одной и группой, как в Excel. Перетащенные id
    (в своём относительном порядке) вставляются перед строкой target_id;
    без target_id — в начало общего списка."""
    ids = [int(i) for i in request.POST.getlist("ids[]") if str(i).isdigit()]
    target_raw = request.POST.get("target_id", "")
    target_id = int(target_raw) if target_raw.isdigit() else None
    if not ids:
        return JsonResponse({"ok": False, "error": "Нечего переставлять"}, status=400)
    all_ids = list(Question.objects.filter(is_active=True).order_by("order", "-updated_at").values_list("id", flat=True))
    moving = [i for i in ids if i in all_ids]
    if not moving:
        return JsonResponse({"ok": False, "error": "Вопросы не найдены"}, status=400)
    remaining = [i for i in all_ids if i not in moving]
    if target_id is not None and target_id in remaining:
        insert_at = remaining.index(target_id)
    else:
        insert_at = 0
    new_order = remaining[:insert_at] + moving + remaining[insert_at:]
    for idx, qid in enumerate(new_order):
        Question.objects.filter(pk=qid).update(order=idx)
    return JsonResponse({"ok": True})


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
@require_POST
def block_quick_add(request):
    """«+ добавить блок» в один клик из выпадающего списка «Все блоки»."""
    form = BlockQuickForm(request.POST)
    if form.is_valid():
        block = form.save()
        if _is_xhr(request):
            return JsonResponse({"ok": True, "id": block.id, "name": block.name, "slug": block.slug, "color": block.color})
        flash.success(request, f"Блок «{block.name}» добавлен")
    else:
        if _is_xhr(request):
            return JsonResponse({"ok": False, "errors": form.errors}, status=400)
        flash.error(request, "Укажите название блока")
    return redirect(_back(request, reverse("finsovet:dashboard")))


@finsovet_required
@require_POST
def responsible_quick_add(request):
    """«+ добавить ответственного» — заводит нового человека по одному имени."""
    form = ResponsibleQuickForm(request.POST)
    if form.is_valid():
        name = form.cleaned_data["name"].strip()
        base = re.sub(r"[^a-zA-Z0-9]", "", _translit(name)).lower() or "person"
        username = base
        n = 1
        while User.objects.filter(username=username).exists():
            n += 1
            username = f"{base}{n}"
        user = User.objects.create(
            username=username, first_name=name, role="manager", is_active=True, is_finsovet_responsible=True,
        )
        user.set_unusable_password()
        user.save(update_fields=["password"])
        if _is_xhr(request):
            return JsonResponse({"ok": True, "id": user.id, "name": name})
        flash.success(request, f"«{name}» добавлен в ответственные")
    else:
        if _is_xhr(request):
            return JsonResponse({"ok": False, "errors": form.errors}, status=400)
        flash.error(request, "Укажите имя")
    return redirect(_back(request, reverse("finsovet:dashboard")))


_TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "zh", "з": "z",
    "и": "i", "й": "i", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r",
    "с": "s", "т": "t", "у": "u", "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
    "ң": "ng", "ө": "o", "ү": "u",
}


def _translit(text: str) -> str:
    return "".join(_TRANSLIT.get(ch, ch) for ch in text.lower())


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


# --------------------------------------------------------------------------- #
#  Долги — совместная доска заметок (принцип Apple Notes / Google Keep):
#  любой с доступом к Финсовету видит и правит все карточки.
# --------------------------------------------------------------------------- #
@finsovet_required
def debts_view(request):
    ctx = {**_base_ctx(), "notes": DebtNote.objects.all()}
    return render(request, "finsovet/debts.html", ctx)


@finsovet_required
@require_POST
def debt_add(request):
    top = DebtNote.objects.order_by("-order").values_list("order", flat=True).first() or 0
    note = DebtNote.objects.create(
        text=request.POST.get("text", "").strip(),
        color=random.choice(DebtNote.COLORS),
        order=top + 1,
        created_by=request.user,
        updated_by=request.user,
    )
    if _is_xhr(request):
        return JsonResponse({"ok": True, "id": note.id})
    return redirect(_back(request, reverse("finsovet:debts")))


@finsovet_required
@require_POST
def debt_update(request, pk):
    note = get_object_or_404(DebtNote, pk=pk)
    field = request.POST.get("field", "")
    value = request.POST.get("value", "")
    if field not in {"text", "color"}:
        return HttpResponseBadRequest("bad field")
    setattr(note, field, value.strip() if field == "text" else value)
    note.updated_by = request.user
    note.save(update_fields=[field, "updated_by", "updated_at"])
    return JsonResponse({"ok": True})


@finsovet_required
@require_POST
def debt_delete(request, pk):
    note = get_object_or_404(DebtNote, pk=pk)
    note.delete()
    if _is_xhr(request):
        return JsonResponse({"ok": True})
    return redirect(_back(request, reverse("finsovet:debts")))
