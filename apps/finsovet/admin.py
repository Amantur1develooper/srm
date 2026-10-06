from django.contrib import admin

from .models import Block, DebtNote, Entry, Question


@admin.register(Block)
class BlockAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "order", "is_active")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("title", "block", "status", "action", "due_date", "responsible", "updated_at")
    list_filter = ("block", "status")
    search_fields = ("title", "action")


@admin.register(Entry)
class EntryAdmin(admin.ModelAdmin):
    list_display = ("question", "kind", "author", "created_at")
    list_filter = ("kind",)
    search_fields = ("text",)


@admin.register(DebtNote)
class DebtNoteAdmin(admin.ModelAdmin):
    list_display = ("__str__", "created_by", "updated_by", "updated_at")
    search_fields = ("text",)
