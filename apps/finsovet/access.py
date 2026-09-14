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


def finsovet_members():
    """Пользователи, которых можно выбрать автором/ответственным (админы + все с доступом)."""
    from django.contrib.auth import get_user_model
    from django.db.models import Q

    User = get_user_model()
    return User.objects.filter(
        Q(can_access_finsovet=True) | Q(role="admin") | Q(is_superuser=True), is_active=True
    ).order_by("first_name", "username")
