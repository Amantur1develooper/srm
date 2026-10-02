from django.urls import path

from . import views

app_name = "finsovet"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("question/add/", views.question_add, name="question_add"),
    path("question/<int:pk>/", views.question_detail, name="question_detail"),
    path("question/<int:pk>/inline/", views.question_inline_update, name="question_inline_update"),
    path("question/<int:pk>/comment/", views.question_comment_add, name="question_comment_add"),

    path("tasks/", views.task_list, name="task_list"),
    path("today/", views.today_view, name="today"),

    path("structure/", views.structure, name="structure"),
]
