"""Импорт листа «Операционка» (Excel) в дерево Финсовета.

Формат листа: ОТДЕЛЫ | НАПРАВЛЕНИЯ | проекты | СТАТУС | статус | дата | комментатор
— это тот же принцип «СЕЙЧАС + история», что и в Финсовете, просто в Excel.
Каждая строка -> запись (Entry) в узле дерева; повтор одного и того же
направления/проекта -> новая запись в истории того же узла, а не дубль.

Использование:
    python manage.py import_operations "<путь к .xlsx>" [--sheet "Операционка"] [--dry-run]
"""
from __future__ import annotations

import datetime as dt
import re

import openpyxl
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.finsovet.models import Entry, Node, Section

User = get_user_model()

# Отдел (колонка A) -> (slug раздела Финсовета, читаемое имя).
# Совпадает с уже посеянными разделами там, где это один и тот же отдел.
DEPARTMENT_TO_SECTION = {
    "ОТДЕЛ ПРОДАЖ": ("sales", "Отдел продаж"),
    "МАРКЕТИНГ": ("marketing", "Маркетинг"),
    "СПЕЦРЕЖИМ": ("specrezhim", "Спецрежим"),
    "ПРОИЗВОДСТВО": ("production", "Производство"),
    "АДМИН": ("admin", "Административное управление"),
    "ФИНАНСЫ": ("finance", "Финансы"),
}

# Частые комментаторы, которых стоит завести пользователями для атрибуции
# (доступ к Финсовету им НЕ выдаётся автоматически — это отдельная галочка).
EXTRA_PEOPLE = {
    "Марат": "marat",
    "Жайнак": "zhainak",
    "Бакыт ака": "bakyt",
}

PROBLEM_MARKERS = ("открытый вопрос", "открыт вопрос")


class Command(BaseCommand):
    help = "Импортирует лист «Операционка» из Excel в дерево Финсовета (разделы -> направления -> проекты)."

    def add_arguments(self, parser):
        parser.add_argument("path", help="Путь к .xlsx файлу")
        parser.add_argument("--sheet", default="Операционка")
        parser.add_argument("--dry-run", action="store_true", help="Только посчитать, ничего не сохранять")

    def handle(self, *args, **options):
        path = options["path"]
        dry = options["dry_run"]
        try:
            wb = openpyxl.load_workbook(path, data_only=True)
        except FileNotFoundError as e:
            raise CommandError(str(e))
        if options["sheet"] not in wb.sheetnames:
            raise CommandError(f"Листа «{options['sheet']}» нет. Есть: {', '.join(wb.sheetnames)}")
        ws = wb[options["sheet"]]

        sections = self._ensure_sections()
        people = self._ensure_people()

        stats = {"nodes": 0, "entries": 0, "rows": 0, "skipped": 0}

        with transaction.atomic():
            self._import_rows(ws, sections, people, stats)
            if dry:
                transaction.set_rollback(True)

        self.stdout.write(self.style.SUCCESS(
            f"{'[DRY-RUN] ' if dry else ''}строк обработано: {stats['rows']}, "
            f"узлов создано/найдено: {stats['nodes']}, записей истории: {stats['entries']}, "
            f"пропущено пустых: {stats['skipped']}"
        ))

    def _ensure_sections(self):
        result = {}
        for i, (dept, (slug, name)) in enumerate(DEPARTMENT_TO_SECTION.items()):
            section, _ = Section.objects.get_or_create(slug=slug, defaults={"name": name, "order": i})
            if section.name != name:
                section.name = name
                section.save(update_fields=["name"])
            result[dept] = section
        return result

    def _ensure_people(self):
        people = {}
        for u in User.objects.all():
            if u.first_name:
                people[u.first_name.strip().lower()] = u
        for name, username in EXTRA_PEOPLE.items():
            if name.lower() in people:
                continue
            u, created = User.objects.get_or_create(
                username=username, defaults={"first_name": name, "role": "manager", "is_active": True}
            )
            if created:
                u.set_unusable_password()
                u.save(update_fields=["password"])
                self.stdout.write(f"создан пользователь для атрибуции: {name} ({username})")
            people[name.lower()] = u
        return people

    def _match_author(self, raw: str, people: dict):
        if not raw:
            return None
        raw_low = raw.lower()
        for name_low, user in people.items():
            if re.search(r"\b" + re.escape(name_low) + r"\b", raw_low):
                return user
        return None

    def _get_or_create_node(self, section, parent, name, stats):
        name = name.strip()
        node, created = Node.objects.get_or_create(section=section, parent=parent, name=name)
        if created:
            stats["nodes"] += 1
        return node

    def _import_rows(self, ws, sections, people, stats):
        current_dept_key = None
        current_section = None
        current_direction = None
        current_date = None

        for row in ws.iter_rows(min_row=4):
            a = self._s(row[0].value) if len(row) > 0 else ""
            b = self._s(row[1].value) if len(row) > 1 else ""
            c = self._s(row[2].value) if len(row) > 2 else ""
            d = self._s(row[3].value) if len(row) > 3 else ""
            f = row[5].value if len(row) > 5 else None
            g = self._s(row[6].value) if len(row) > 6 else ""

            if a:
                current_dept_key = next((k for k in DEPARTMENT_TO_SECTION if k in a.upper()), a.upper())
                current_section = sections.get(current_dept_key)
                current_direction = None
            if not current_section:
                continue  # строка до первого встреченного отдела

            if b:
                current_direction = self._get_or_create_node(current_section, None, b, stats)

            if isinstance(f, dt.datetime):
                current_date = f

            if not c and not d:
                stats["skipped"] += 1
                continue

            stats["rows"] += 1
            target = self._get_or_create_node(current_section, current_direction, c, stats) if c else current_direction
            if target is None or not d:
                continue

            text = d
            kind = Entry.Kind.PROBLEM if any(m in d.lower() for m in PROBLEM_MARKERS) else Entry.Kind.STATE
            author = self._match_author(g, people)
            if g:
                text = f"{d}\n\n👤 {g}"

            entry = Entry.objects.create(node=target, kind=kind, text=text, author=author)
            if current_date:
                aware = timezone.make_aware(dt.datetime.combine(current_date.date(), dt.time(12, 0)))
                Entry.objects.filter(pk=entry.pk).update(created_at=aware)
            stats["entries"] += 1

    @staticmethod
    def _s(v):
        if v is None:
            return ""
        return str(v).strip()
