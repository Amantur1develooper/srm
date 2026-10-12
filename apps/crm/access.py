"""Разграничение доступа к данным по ролям."""
from __future__ import annotations

from django.core.exceptions import PermissionDenied


def clients_for(user):
    from .models import Client

    qs = Client.objects.select_related("stage", "manager")
    if user.can_see_all_clients:
        return qs
    return qs.filter(manager=user)


def tasks_for(user):
    from .models import Task

    qs = Task.objects.select_related("client", "client__stage", "manager")
    if user.can_see_all_clients:
        return qs
    return qs.filter(manager=user)


def own_tasks_for(user):
    """Только свои задачи — для раздела «Задачи», счётчиков и «Мои задачи» на главной.
    Чужие задачи админ/руководитель по-прежнему открывают из карточки клиента."""
    return tasks_for(user).filter(manager=user)


def messages_for(user):
    from .models import Message

    qs = Message.objects.select_related("client", "template", "manager")
    if user.can_see_all_clients:
        return qs
    return qs.filter(manager=user)


def ensure_client_access(user, client):
    if user.can_see_all_clients:
        return
    if client.manager_id != user.id:
        raise PermissionDenied("Нет доступа к этому клиенту")


def ensure_settings(user):
    if not user.can_manage_settings:
        raise PermissionDenied("Доступно только администратору")
