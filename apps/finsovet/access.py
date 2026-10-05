"""Доступ к Финсовету: залогинен + флаг can_access_finsovet (или админ)."""
from __future__ import annotations

from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def finsovet_required(view):
    @wraps(view)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not request.user.has_finsovet_access:
            raise PermissionDenied("Нет доступа к Финсовету")
        return view(request, *args, **kwargs)

    return wrapper


def responsible_people():
    """Список ответственных — только из него выбирают, без ручного ввода имени.
    Пополняется через «+ добавить ответственного» (флаг is_finsovet_responsible)."""
    from django.contrib.auth import get_user_model

    User = get_user_model()
    return User.objects.filter(is_finsovet_responsible=True, is_active=True).order_by("first_name")


# Исторический алиас — используется там же, где раньше выбирали «кто сообщил».
finsovet_members = responsible_people
