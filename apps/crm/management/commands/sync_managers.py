"""Приводит список менеджеров к согласованному: Айниса, Минаим, Минура, Айбек, Куба, Аман.

Создаёт недостающих (с паролем по умолчанию), остальных активных менеджеров,
которых нет в списке, — деактивирует (не удаляет: их клиенты/задачи/история
остаются как есть, просто менеджер пропадает из выпадающих списков).

    python manage.py sync_managers
    python manage.py sync_managers --password ВашПароль
"""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

User = get_user_model()

MANAGERS = ["Айниса", "Минаим", "Минура", "Айбек", "Куба", "Аман"]

_TRANSLIT = str.maketrans(
    "абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
    "abvgdeejzijklmnoprstufhccss'y'euq",
)


def _username(name: str) -> str:
    return name.strip().lower().translate(_TRANSLIT)


class Command(BaseCommand):
    help = "Синхронизирует список менеджеров с согласованным (Айниса/Минаим/Минура/Айбек/Куба/Аман)"

    def add_arguments(self, parser):
        parser.add_argument("--password", default="webordo123", help="пароль для новых менеджеров")

    @transaction.atomic
    def handle(self, *args, **opts):
        keep_usernames = set()
        for name in MANAGERS:
            username = _username(name)
            keep_usernames.add(username)
            user, created = User.objects.get_or_create(
                username=username,
                defaults={"first_name": name, "role": "manager", "is_active": True},
            )
            changed = False
            if not user.is_active:
                user.is_active = True
                changed = True
            if user.role != "manager":
                user.role = "manager"
                changed = True
            if created:
                user.set_password(opts["password"])
                changed = True
            if changed:
                user.save()
            self.stdout.write(("+ создан " if created else "= есть   ") + f"{username} ({name})")

        others = User.objects.filter(role="manager", is_active=True).exclude(username__in=keep_usernames)
        for u in others:
            u.is_active = False
            u.save(update_fields=["is_active"])
            self.stdout.write(self.style.WARNING(f"- деактивирован: {u.username} ({u.display_name})"))

        self.stdout.write(self.style.SUCCESS("Готово."))
