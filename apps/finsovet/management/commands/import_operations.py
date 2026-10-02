"""Импорт листа «Операционка» (Excel) в плоскую таблицу вопросов Финсовета.

Формат листа: ОТДЕЛЫ | НАПРАВЛЕНИЯ | проекты | СТАТУС | статус | дата | комментатор
Каждая содержательная строка -> Вопрос (Block + название) с записью в истории.
Повтор одного и того же направления/проекта в блоке -> не новый вопрос,
а новая запись в истории уже существующего.

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

from apps.finsovet.models import Block, Entry, Question

User = get_user_model()

# Отдел (колонка A) -> блок по умолчанию (для направлений этого отдела).
DEPARTMENT_TO_BLOCK = {
    "ОТДЕЛ ПРОДАЖ": "Продажи",
    "МАРКЕТИНГ": "Маркетинг",
    "СПЕЦРЕЖИМ": "Спецрежим",
    "АДМИН": "Общие",
    "ФИНАНСЫ": "Финансы",
}
# Для «ПРОИЗВОДСТВО» блоком становится само направление (колонка B) —
# совпадает со списком блоков в ТЗ.
PRODUCTION_DIRECTION_TO_BLOCK = {
    "АЛА ТОО": "Ала Тоо",
    "ЭКО ПАРК": "Эко Парк",
    "К БЛОК": "К Блок",
    "ЖЗИ": "ЖЗИ",
    "АБВГ": "АБВ",
    "ДЕ": "ДЕ",
}

EXTRA_PEOPLE = {
    "Марат": "marat",
    "Жайнак": "zhainak",
    "Бакыт ака": "bakyt",
}


class Command(BaseCommand):
    help = "Импортирует лист «Операционка» из Excel в таблицу вопросов Финсовета."

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

        people = self._ensure_people()
        stats = {"questions": 0, "entries": 0, "rows": 0, "skipped": 0}

        with transaction.atomic():
            self._import_rows(ws, people, stats)
            if dry:
                transaction.set_rollback(True)

        self.stdout.write(self.style.SUCCESS(
            f"{'[DRY-RUN] ' if dry else ''}строк обработано: {stats['rows']}, "
            f"вопросов создано/найдено: {stats['questions']}, записей истории: {stats['entries']}, "
            f"пропущено пустых: {stats['skipped']}"
        ))

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

    def _get_block(self, name, cache):
        name = name.strip()
        if name in cache:
            return cache[name]
        block, _ = Block.objects.get_or_create(name=name, defaults={"slug": self._slug(name), "order": 99})
        cache[name] = block
        return block

    @staticmethod
    def _slug(name):
        import uuid

        base = "".join(ch for ch in name.lower() if ch.isalnum())[:60]
        return f"{base}-{uuid.uuid4().hex[:6]}" if base else f"block-{uuid.uuid4().hex[:8]}"

    def _get_or_create_question(self, block, title, stats):
        title = title.strip()[:300]
        q, created = Question.objects.get_or_create(block=block, title=title)
        if created:
            stats["questions"] += 1
        return q

    def _import_rows(self, ws, people, stats):
        block_cache = {}
        current_dept = None
        current_direction = None  # для ПРОИЗВОДСТВА: название направления (= блок)
        current_block = None      # для остальных отделов: блок всей секции
        current_date = None

        for row in ws.iter_rows(min_row=4):
            a = self._s(row[0].value) if len(row) > 0 else ""
            b = self._s(row[1].value) if len(row) > 1 else ""
            c = self._s(row[2].value) if len(row) > 2 else ""
            d = self._s(row[3].value) if len(row) > 3 else ""
            f = row[5].value if len(row) > 5 else None
            e = row[4].value if len(row) > 4 else None
            g = self._s(row[6].value) if len(row) > 6 else ""

            if a:
                current_dept = next((k for k in list(DEPARTMENT_TO_BLOCK) + ["ПРОИЗВОДСТВО"] if k in a.upper()), a.upper())
                current_direction = None
                current_block = None
                if current_dept != "ПРОИЗВОДСТВО":
                    block_name = DEPARTMENT_TO_BLOCK.get(current_dept, current_dept.title())
                    current_block = self._get_block(block_name, block_cache)

            if b:
                if current_dept == "ПРОИЗВОДСТВО":
                    b_up = b.strip().upper()
                    block_name = next((v for k, v in PRODUCTION_DIRECTION_TO_BLOCK.items() if k in b_up), b.strip())
                    current_direction = self._get_block(block_name, block_cache)
                else:
                    current_block = self._get_block(DEPARTMENT_TO_BLOCK.get(current_dept, current_dept or b), block_cache) if current_dept else current_block

            target_block = current_direction if current_dept == "ПРОИЗВОДСТВО" else current_block
            if target_block is None:
                continue  # строка до первого встреченного отдела/направления

            date_val = f if isinstance(f, dt.datetime) else (e if isinstance(e, dt.datetime) else None)
            if date_val:
                current_date = date_val

            if not c and not d and not b:
                stats["skipped"] += 1
                continue
            if not d:
                stats["skipped"] += 1
                continue

            stats["rows"] += 1
            # В ПРОИЗВОДСТВЕ: конкретная работа (C) -> вопрос; без C -> общий вопрос по блоку.
            # В остальных отделах: направление (B) -> вопрос.
            if current_dept == "ПРОИЗВОДСТВО":
                title = c if c else (b if b else target_block.name)
            else:
                title = b if b else target_block.name
            question = self._get_or_create_question(target_block, title, stats)

            author = self._match_author(g, people)
            text = d if not g else f"{d}\n\n👤 {g}"
            entry = Entry.objects.create(question=question, kind=Entry.Kind.COMMENT, text=text, author=author)
            if current_date:
                aware = timezone.make_aware(dt.datetime.combine(current_date.date(), dt.time(12, 0)))
                Entry.objects.filter(pk=entry.pk).update(created_at=aware)
                Question.objects.filter(pk=question.pk).update(updated_at=aware)
            stats["entries"] += 1

    @staticmethod
    def _s(v):
        if v is None:
            return ""
        return str(v).strip()
