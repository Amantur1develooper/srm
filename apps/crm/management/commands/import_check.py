"""Разбор Excel-файла импорта без записи в базу (dry-run).

    python manage.py import_check "ЛИДЫ с БАЗЫ.xlsx"
    python manage.py import_check файл.xlsx --sheet 0 --strategy skip
"""
from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.crm.services import excel_import


class Command(BaseCommand):
    help = "Показывает, что произойдёт при импорте файла, и почему строки пропускаются"

    def add_arguments(self, parser):
        parser.add_argument("path")
        parser.add_argument("--sheet", type=int, default=None, help="индекс листа (по умолчанию — с макс. числом строк)")
        parser.add_argument("--strategy", default="skip", choices=["skip", "update", "create"])

    def handle(self, *args, **opts):
        path = Path(opts["path"])
        if not path.is_absolute():
            path = Path(settings.BASE_DIR) / path
        if not path.exists():
            self.stderr.write(self.style.ERROR(f"Файл не найден: {path}"))
            return

        raw = path.read_bytes()
        previews = excel_import.preview_workbook(raw)
        for i, p in enumerate(previews):
            self.stdout.write(f"[{i}] лист «{p.sheet_name}»: строк данных {p.total_rows}, "
                              f"заголовок в строке {p.header_row + 1}")
            self.stdout.write(f"    колонки: {p.headers}")
            self.stdout.write(f"    автосопоставление: {p.suggested_mapping}")

        idx = opts["sheet"]
        preview = previews[idx] if idx is not None else max(previews, key=lambda p: p.total_rows)
        self.stdout.write(self.style.WARNING(f"\n=== Разбор листа «{preview.sheet_name}», стратегия: {opts['strategy']} ===\n"))

        res = excel_import.run_import(
            file_bytes=raw,
            filename=path.name,
            sheet_name=preview.sheet_name,
            header_row=preview.header_row,
            mapping=preview.suggested_mapping,
            duplicate_strategy=opts["strategy"],
            dry_run=True,
        )
        self.stdout.write(f"Будет обработано строк: {res.total}")
        self.stdout.write(self.style.SUCCESS(f"  создано:   {res.created}"))
        self.stdout.write(f"  обновлено: {res.updated}")
        self.stdout.write(self.style.WARNING(f"  пропущено: {res.skipped}"))

        if "full_name" not in preview.suggested_mapping:
            self.stdout.write(self.style.ERROR("\n⚠ Колонка ФИО не определена автоматически — "
                                               "укажите её вручную в веб-интерфейсе."))
        if res.noname_rows:
            self.stdout.write(f"\nБез имени ({len(res.noname_rows)}): строки "
                              + ", ".join(str(r['row']) for r in res.noname_rows[:30])
                              + (" …" if len(res.noname_rows) > 30 else ""))
        if res.skipped_rows:
            self.stdout.write(self.style.WARNING(f"\nПропущенные строки ({len(res.skipped_rows)}):"))
            for r in res.skipped_rows:
                self.stdout.write(f"  строка {r['row']}: {r['name']} / {r['phone'] or '—'} — {r['reason']}")
        if res.empty_rows:
            self.stdout.write(f"\nПустые строки: {', '.join(map(str, res.empty_rows))}")
