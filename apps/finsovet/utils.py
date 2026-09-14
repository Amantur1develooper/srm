from __future__ import annotations


def log_entry(node, kind, text, author=None):
    from .models import Entry

    return Entry.objects.create(node=node, kind=kind, text=text, author=author)


def log_task_event(task, text, author=None):
    from .models import TaskEvent

    return TaskEvent.objects.create(task=task, text=text, author=author)
