from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from apps.finsovet.models import Block

User = get_user_model()

# (название, цвет)
BLOCKS = [
    ("К Блок", "#f97316"),      # оранжевый
    ("ЖЗИ", "#0891b2"),
    ("Эко Парк", "#10b981"),    # изумрудный
    ("Ала Тоо", "#e8dcc8"),     # молочно-бежевый
    ("АБВ", "#8e8e93"),         # серый
    ("ДЕ", "#8e8e93"),          # серый
    ("Общие", "#64748b"),
    ("Финансы", "#2563eb"),     # синий
    ("Продажи", "#dc2626"),     # красный
    ("Маркетинг", "#f59e0b"),   # жёлтый
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
        for i, (name, color) in enumerate(BLOCKS):
            slug = f"block-{i}-{''.join(ch for ch in name.lower() if ch.isalnum())}"[:95]
            block, created = Block.objects.get_or_create(
                name=name, defaults={"slug": slug, "order": i, "color": color}
            )
            if not created and block.color != color:
                block.color = color
                block.save(update_fields=["color"])
            self.stdout.write(("создан блок: " if created else "уже есть: ") + name)

        for username, name in PEOPLE:
            user, created = User.objects.get_or_create(
                username=username, defaults={"first_name": name, "role": "manager", "is_active": True}
            )
            changed = []
            if created:
                user.set_unusable_password()
                changed.append("password")
                self.stdout.write(f"создан пользователь: {name} ({username})")
            if not user.first_name:
                user.first_name = name
                changed.append("first_name")
            if not user.is_finsovet_responsible:
                user.is_finsovet_responsible = True
                changed.append("is_finsovet_responsible")
            if changed:
                user.save(update_fields=changed)
