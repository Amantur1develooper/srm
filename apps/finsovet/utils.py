from __future__ import annotations


def log_entry(question, kind, text, author=None):
    from .models import Entry

    return Entry.objects.create(question=question, kind=kind, text=text, author=author)


def log_change(question, text, author=None):
    """Автозапись об изменении поля (статус/действие/срок/ответственный) — для истории."""
    from .models import Entry

    return log_entry(question, Entry.Kind.CHANGE, text, author)
