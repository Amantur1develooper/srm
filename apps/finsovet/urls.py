from django.urls import path

from . import views

app_name = "finsovet"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("node/<int:pk>/", views.node_detail, name="node_detail"),
    path("node/<int:pk>/state/", views.node_state_update, name="node_state_update"),
    path("node/<int:pk>/comment/", views.node_comment_add, name="node_comment_add"),
    path("node/<int:pk>/task/", views.node_task_add, name="node_task_add"),
    path("entry/add/", views.entry_add, name="entry_add"),
    path("message/add/", views.object_message_add, name="object_message_add"),

    path("tasks/", views.task_list, name="task_list"),
    path("tasks/add/", views.task_add, name="task_add"),
    path("tasks/<int:pk>/", views.task_detail, name="task_detail"),
    path("tasks/<int:pk>/status/", views.task_status, name="task_status"),
    path("tasks/<int:pk>/inline/", views.task_inline_update, name="task_inline_update"),

    path("decisions/", views.decisions_list, name="decisions_list"),
    path("decisions/add/", views.decision_add, name="decision_add"),

    path("changes/", views.changes_view, name="changes"),

    path("protocol/", views.protocol_list, name="protocol_list"),
    path("protocol/generate/", views.protocol_generate, name="protocol_generate"),
    path("protocol/<int:pk>/", views.protocol_detail, name="protocol_detail"),

    path("structure/", views.structure, name="structure"),
    path("structure/node/<int:pk>/deactivate/", views.node_deactivate, name="node_deactivate"),
]
