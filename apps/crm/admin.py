from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import (
    BroadcastBatch,
    Client,
    ClientHistory,
    Comment,
    Funnel,
    ImportLog,
    Message,
    MessageTemplate,
    Notification,
    Stage,
    Task,
    User,
    WhatsAppAction,
)


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    list_display = ("username", "display_name", "role", "phone", "is_active", "is_staff")
    list_filter = ("role", "is_active", "is_staff")
    fieldsets = DjangoUserAdmin.fieldsets + (
        ("CRM", {"fields": ("role", "phone", "is_active_manager")}),
    )


@admin.register(Stage)
class StageAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "order", "in_funnel", "is_won", "is_lost", "is_active")
    list_editable = ("order", "in_funnel", "is_won", "is_lost", "is_active")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Funnel)
class FunnelAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "order", "is_active")
    list_editable = ("order", "is_active")
    prepopulated_fields = {"slug": ("name",)}


class HistoryInline(admin.TabularInline):
    model = ClientHistory
    extra = 0
    readonly_fields = ("kind", "text", "user", "created_at")
    can_delete = False


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ("full_name", "phone", "stage", "funnel", "manager", "source", "created_at")
    list_filter = ("stage", "funnel", "manager", "source")
    search_fields = ("full_name", "phone", "phone_normalized", "looking_for", "comment")
    autocomplete_fields = ("manager",)
    inlines = [HistoryInline]


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ("title", "client", "manager", "due_date", "due_time", "status")
    list_filter = ("status", "manager")
    search_fields = ("title", "client__full_name")


@admin.register(MessageTemplate)
class MessageTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active", "created_by", "updated_at")


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ("client", "template", "manager", "status", "created_at", "sent_at")
    list_filter = ("status",)


admin.site.register(Comment)
admin.site.register(ClientHistory)
admin.site.register(WhatsAppAction)
admin.site.register(BroadcastBatch)
admin.site.register(Notification)
admin.site.register(ImportLog)

admin.site.site_header = "Webordo CRM"
admin.site.site_title = "Webordo CRM"
admin.site.index_title = "Администрирование"
