"""Доступ к Финсовету: залогинен + флаг can_access_finsovet (или админ)."""
from __future__ import annotations

from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

# Фиксированный список ответственных — выбор только из них, без ручного ввода.
# Список можно расширять: добавить пользователя с таким username.
RESPONSIBLE_USERNAMES = ["marat", "zhainak", "bakyt", "maksat", "doolotake", "azamat"]


def finsovet_required(view):
    @wraps(view)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not request.user.has_finsovet_access:
            raise PermissionDenied("Нет доступа к Финсовету")
        return view(request, *args, **kwargs)

    return wrapper


def responsible_people():
    """Фиксированный список ответственных (Марат, Жайнак, Бакыт аке, Максат, Дөөлөт аке, Азамат)."""
    from django.contrib.auth import get_user_model

    User = get_user_model()
    return User.objects.filter(username__in=RESPONSIBLE_USERNAMES, is_active=True).order_by("first_name")


# Исторический алиас — используется там же, где раньше выбирали «кто сообщил».
finsovet_members = responsible_people
