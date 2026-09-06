from django.db import migrations


def backfill(apps, schema_editor):
    from apps.crm.utils import normalize_phone

    Client = apps.get_model("crm", "Client")
    to_update = []
    for c in Client.objects.all().only("id", "phone", "phone_normalized"):
        norm = normalize_phone(c.phone)
        if norm != c.phone_normalized:
            c.phone_normalized = norm
            to_update.append(c)
    if to_update:
        Client.objects.bulk_update(to_update, ["phone_normalized"], batch_size=500)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "0004_client_last_activity_at_client_last_contact_at"),
    ]

    operations = [
        migrations.RunPython(backfill, noop),
    ]
