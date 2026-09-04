from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.utils import timezone

from .access import tasks_for
from .models import Message, Notification, Task


def _asset_version():
    """Метка версии статики (mtime app.css) — чтобы браузер подхватывал изменения."""
    try:
        css = Path(settings.BASE_DIR) / "static" / "crm" / "app.css"
        js = Path(settings.BASE_DIR) / "static" / "crm" / "app.js"
        return str(int(max(css.stat().st_mtime, js.stat().st_mtime)))
    except OSError:
        return "1"


def crm_globals(request):
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {"asset_version": _asset_version()}

    today = timezone.localdate()
    open_tasks = tasks_for(user).filter(status__in=[Task.Status.NEW, Task.Status.IN_PROGRESS])
    overdue = sum(1 for t in open_tasks.filter(due_date__lt=today))
    today_cnt = open_tasks.filter(due_date=today).count()

    return {
        "asset_version": _asset_version(),
        "nav_tasks_today": today_cnt,
        "nav_tasks_overdue": overdue,
        "nav_notifications": Notification.objects.filter(user=user, is_read=False).count(),
        "nav_recent_notifications": Notification.objects.filter(user=user)[:8],
        "nav_prepared_messages": (
            Message.objects.filter(status=Message.Status.PREPARED)
            if user.can_see_all_clients
            else Message.objects.filter(manager=user, status=Message.Status.PREPARED)
        ).count(),
    }
