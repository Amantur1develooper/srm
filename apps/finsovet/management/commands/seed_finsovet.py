from django.core.management.base import BaseCommand

from apps.finsovet.models import Section

SECTIONS = [
    ("finance", "Финансы"),
    ("sales", "Продажи и маркетинг"),
    ("admin", "Административное управление"),
    ("production", "Производство"),
]


class Command(BaseCommand):
    help = "Создаёт базовые разделы Финсовета (если их ещё нет)."

    def handle(self, *args, **options):
        for i, (slug, name) in enumerate(SECTIONS):
            section, created = Section.objects.get_or_create(slug=slug, defaults={"name": name, "order": i})
            if not created and section.name != name:
                section.name = name
                section.save(update_fields=["name"])
            self.stdout.write(("создан: " if created else "уже есть: ") + name)
