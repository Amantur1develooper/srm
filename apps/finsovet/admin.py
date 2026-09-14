from django.contrib import admin

from .models import Decision, Entry, Meeting, Node, Section, Task, TaskEvent


@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "order", "is_active")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Node)
class NodeAdmin(admin.ModelAdmin):
    list_display = ("name", "section", "parent", "order", "is_active")
    list_filter = ("section", "is_active")
    search_fields = ("name",)


@admin.register(Entry)
class EntryAdmin(admin.ModelAdmin):
    list_display = ("node", "kind", "author", "created_at")
    list_filter = ("kind",)
    search_fields = ("text",)


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ("title", "node", "assignee", "due_date", "status")
    list_filter = ("status",)
    search_fields = ("title",)


@admin.register(TaskEvent)
class TaskEventAdmin(admin.ModelAdmin):
    list_display = ("task", "text", "created_at")


@admin.register(Decision)
class DecisionAdmin(admin.ModelAdmin):
    list_display = ("text", "section", "node", "responsible", "due_date", "created_at")


@admin.register(Meeting)
class MeetingAdmin(admin.ModelAdmin):
    list_display = ("date", "created_by", "created_at")
