from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path("accounts/login/", auth_views.LoginView.as_view(template_name="crm/login.html"), name="login"),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),

    path("", views.dashboard, name="dashboard"),
    path("search/", views.global_search, name="search"),

    # Клиенты
    path("clients/", views.client_list, name="client_list"),
    path("clients/export/", views.client_export, name="client_export"),
    path("clients/bulk/", views.client_bulk_action, name="client_bulk"),
    path("clients/bulk/task/", views.client_bulk_task, name="client_bulk_task"),
    path("clients/new/", views.client_create, name="client_create"),
    path("clients/<int:pk>/", views.client_detail, name="client_detail"),
    path("clients/<int:pk>/edit/", views.client_edit, name="client_edit"),
    path("clients/<int:pk>/stage/", views.client_change_stage, name="client_change_stage"),
    path("clients/<int:pk>/comment/", views.client_add_comment, name="client_add_comment"),
    path("clients/<int:pk>/task/", views.client_add_task, name="client_add_task"),
    path("clients/<int:pk>/whatsapp/", views.client_whatsapp, name="client_whatsapp"),
    path("clients/<int:pk>/inline/", views.client_inline_update, name="client_inline_update"),

    # Канбан
    path("kanban/", views.kanban, name="kanban"),
    path("kanban/move/", views.kanban_move, name="kanban_move"),
    path("kanban/quick-add/", views.client_quick_create, name="client_quick_create"),

    # Задачи
    path("tasks/", views.task_list, name="task_list"),
    path("tasks/new/", views.task_create, name="task_create"),
    path("tasks/<int:pk>/", views.task_detail, name="task_detail"),
    path("tasks/<int:pk>/status/", views.task_set_status, name="task_set_status"),
    path("tasks/<int:pk>/inline/", views.task_inline_update, name="task_inline_update"),
    path("tasks/<int:pk>/repeat/", views.task_repeat, name="task_repeat"),
    path("tasks/<int:pk>/message/", views.task_make_message, name="task_make_message"),

    # Сообщения и шаблоны
    path("messages/", views.message_list, name="message_list"),
    path("messages/<int:pk>/status/", views.message_set_status, name="message_set_status"),
    path("templates/", views.template_list, name="template_list"),
    path("templates/new/", views.template_create, name="template_create"),
    path("templates/<int:pk>/edit/", views.template_edit, name="template_edit"),
    path("templates/<int:pk>/delete/", views.template_delete, name="template_delete"),

    # Массовая рассылка
    path("broadcast/", views.broadcast_start, name="broadcast_start"),
    path("broadcast/<int:pk>/run/", views.broadcast_run, name="broadcast_run"),

    # Импорт
    path("import/", views.import_upload, name="import_upload"),
    path("import/map/", views.import_map, name="import_map"),
    path("import/run/", views.import_run, name="import_run"),
    path("import/finish/", views.import_finish, name="import_finish"),

    # Уведомления
    path("notifications/", views.notifications, name="notifications"),
    path("notifications/read/", views.notifications_read_all, name="notifications_read_all"),

    # Администрирование
    path("admin-panel/users/", views.admin_users, name="admin_users"),
    path("admin-panel/users/new/", views.admin_user_create, name="admin_user_create"),
    path("admin-panel/users/<int:pk>/", views.admin_user_edit, name="admin_user_edit"),
    path("admin-panel/stages/", views.admin_stages, name="admin_stages"),
]
