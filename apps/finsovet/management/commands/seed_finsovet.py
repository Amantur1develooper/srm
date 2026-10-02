from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from apps.finsovet.models import Block

User = get_user_model()

BLOCKS = [
    "К Блок", "ЖЗИ", "Эко Парк", "Ала Тоо", "АБВ", "ДЕ",
    "Общие", "Финансы", "Продажи", "Маркетинг",
]

# Фиксированный список ответственных (username, имя).
PEOPLE = [
    ("marat", "Марат"),
    ("zhainak", "Жайнак"),
    ("bakyt", "Бакыт аке"),
    ("maksat", "Максат"),
    ("doolotake", "Дөөлөт аке"),
    ("azamat", "Азамат"),
]


class Command(BaseCommand):
    help = "Создаёт базовые блоки и ответственных Финсовета (если их ещё нет)."

    def handle(self, *args, **options):
        for i, name in enumerate(BLOCKS):
            slug = f"block-{i}-{''.join(ch for ch in name.lower() if ch.isalnum())}"[:95]
            block, created = Block.objects.get_or_create(
                name=name, defaults={"slug": slug, "order": i}
            )
            self.stdout.write(("создан блок: " if created else "уже есть: ") + name)

        for username, name in PEOPLE:
            user, created = User.objects.get_or_create(
                username=username, defaults={"first_name": name, "role": "manager", "is_active": True}
            )
            if created:
                user.set_unusable_password()
                user.save(update_fields=["password"])
                self.stdout.write(f"создан пользователь: {name} ({username})")
            elif not user.first_name:
                user.first_name = name
                user.save(update_fields=["first_name"])
