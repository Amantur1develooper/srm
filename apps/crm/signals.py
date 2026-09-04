from django.db.models.signals import pre_save
from django.dispatch import receiver

from .models import Client
from .utils import normalize_phone


@receiver(pre_save, sender=Client)
def set_normalized_phone(sender, instance: Client, **kwargs):
    instance.phone_normalized = normalize_phone(instance.phone)
