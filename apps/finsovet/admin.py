from django.contrib import admin

from .models import Block, DebtNote, Entry, ExpectedFund, Payment, PaymentRecord, Question


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


class PaymentRecordInline(admin.TabularInline):
    model = PaymentRecord
    extra = 0


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("name", "due", "total", "is_active", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("name", "notes")
    inlines = [PaymentRecordInline]


@admin.register(ExpectedFund)
class ExpectedFundAdmin(admin.ModelAdmin):
    list_display = ("source", "amount", "due", "is_active", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("source", "notes")
