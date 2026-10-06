from django.db import migrations


def add_funnel(apps, schema_editor):
    Funnel = apps.get_model("crm", "Funnel")
    if Funnel.objects.filter(name="ЖЗИ").exclude(slug="zhzi").exists():
        return  # уже заведена вручную через админку
    Funnel.objects.update_or_create(slug="zhzi", defaults={"name": "ЖЗИ", "order": 30, "is_active": True})


def remove_funnel(apps, schema_editor):
    apps.get_model("crm", "Funnel").objects.filter(slug="zhzi").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "0007_user_is_finsovet_responsible"),
    ]

    operations = [
        migrations.RunPython(add_funnel, remove_funnel),
    ]
