"""Начальное наполнение CRM: стадии, роли, демо-пользователи, шаблоны.

Использование:
    python manage.py seed_crm
    python manage.py seed_crm --demo-users --import "ЛОГИКА СРМ.xlsx"
"""
from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.crm.models import Funnel, MessageTemplate, Stage

User = get_user_model()

STAGES = [
    # slug, name, order, color, in_funnel, is_won, is_lost
    ("new", "Новая заявка", 10, "#3b82f6", True, False, False),
    ("accepted", "Принята", 20, "#6366f1", True, False, False),
    ("consult", "Консультация", 30, "#8b5cf6", True, False, False),
    ("hot", "Горячий", 40, "#ef4444", True, False, False),
    ("won", "Сделка", 50, "#22c55e", True, True, False),
    ("cold", "Холодный", 60, "#0ea5e9", False, False, False),
    ("frozen", "Заморожен", 70, "#94a3b8", False, False, False),
    ("lost", "Проигранные", 80, "#64748b", False, False, True),
]

FUNNELS = [
    ("el-nasip", "Эл Насип", 10),
    ("standart-house", "Standart House", 20),
]

TEMPLATES = [
    ("Приглашение на просмотр",
     "Здравствуйте, {имя}! Хотели пригласить вас на просмотр объекта ({объект}). "
     "Когда вам будет удобно? На связи — {менеджер}."),
    ("Первый контакт",
     "Здравствуйте, {имя}! Меня зовут {менеджер}, я из компании Webordo. "
     "Вы оставляли заявку — подскажите, что рассматриваете?"),
    ("Напоминание",
     "{имя}, добрый день! Напоминаю о себе по вашему запросу «{объект}». "
     "Готов ответить на вопросы. — {менеджер}"),
    ("Отправка предложения",
     "{имя}, здравствуйте! Подготовил для вас варианты по бюджету {бюджет}. "
     "Отправляю подборку, посмотрите, пожалуйста."),
]


class Command(BaseCommand):
    help = "Наполняет CRM начальными данными"

    def add_arguments(self, parser):
        parser.add_argument("--demo-users", action="store_true", help="создать демо-пользователей")
        parser.add_argument("--import", dest="import_path", help="путь к .xlsx для импорта клиентов")

    @transaction.atomic
    def handle(self, *args, **opts):
        for slug, name, order, color, in_funnel, won, lost in STAGES:
            Stage.objects.update_or_create(
                slug=slug,
                defaults=dict(
                    name=name, order=order, color=color, in_funnel=in_funnel,
                    is_won=won, is_lost=lost, is_active=True,
                ),
            )
        self.stdout.write(self.style.SUCCESS(f"Стадии: {Stage.objects.count()}"))

        for slug, name, order in FUNNELS:
            Funnel.objects.update_or_create(slug=slug, defaults=dict(name=name, order=order, is_active=True))
        self.stdout.write(self.style.SUCCESS(f"Воронки: {Funnel.objects.count()}"))

        for name, body in TEMPLATES:
            MessageTemplate.objects.get_or_create(name=name, defaults={"body": body})
        self.stdout.write(self.style.SUCCESS(f"Шаблоны: {MessageTemplate.objects.count()}"))

        if opts["demo_users"]:
            self._demo_users()

        if opts["import_path"]:
            self._import(opts["import_path"])

    def _demo_users(self):
        specs = [
            ("admin", "Администратор", "", "admin", True, True),
            ("head", "Руководитель", "Отдела продаж", "head", False, False),
            ("azamat", "Азамат", "", "manager", False, False),
            ("kuba", "Куба", "", "manager", False, False),
            ("minura", "Минура", "", "manager", False, False),
            ("ajbek", "Айбек", "", "manager", False, False),
            ("minajym", "Минайым", "", "manager", False, False),
            ("ajnisa", "Айниса", "", "manager", False, False),
        ]
        for username, first, last, role, is_super, is_staff in specs:
            u, created = User.objects.get_or_create(
                username=username,
                defaults=dict(first_name=first, last_name=last, role=role,
                              is_superuser=is_super, is_staff=is_super or is_staff),
            )
            if created:
                u.set_password("webordo123")
                u.save()
                self.stdout.write(f"  + {username} / webordo123 ({role})")
            else:
                self.stdout.write(f"  = {username} уже существует")

    def _import(self, path_str):
        from apps.crm.services import excel_import

        path = Path(path_str)
        if not path.is_absolute():
            path = Path(settings.BASE_DIR) / path
        if not path.exists():
            self.stderr.write(self.style.ERROR(f"Файл не найден: {path}"))
            return
        raw = path.read_bytes()
        previews = excel_import.preview_workbook(raw)
        # берём лист с максимумом строк данных
        best = max(previews, key=lambda p: p.total_rows)
        self.stdout.write(f"Импорт из листа «{best.sheet_name}», строк: {best.total_rows}")
        self.stdout.write(f"Автосопоставление: {best.suggested_mapping}")
        default_manager = User.objects.filter(role="manager").first()
        result = excel_import.run_import(
            file_bytes=raw,
            filename=path.name,
            sheet_name=best.sheet_name,
            header_row=best.header_row,
            mapping=best.suggested_mapping,
            duplicate_strategy="skip",
            default_manager=default_manager,
            user=User.objects.filter(is_superuser=True).first(),
        )
        self.stdout.write(self.style.SUCCESS(
            f"Импорт: создано {result.created}, обновлено {result.updated}, "
            f"пропущено {result.skipped}, всего {result.total}"
        ))
        for e in result.errors:
            self.stderr.write(self.style.ERROR(e))
