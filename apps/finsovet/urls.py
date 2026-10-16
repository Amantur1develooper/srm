from django.urls import path

from . import views

app_name = "finsovet"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("question/add/", views.question_add, name="question_add"),
    path("question/<int:pk>/", views.question_detail, name="question_detail"),
    path("question/<int:pk>/inline/", views.question_inline_update, name="question_inline_update"),
    path("question/<int:pk>/comment/", views.question_comment_add, name="question_comment_add"),
    path("question/<int:pk>/delete/", views.question_delete, name="question_delete"),
    path("question/reorder/", views.question_reorder, name="question_reorder"),

    path("tasks/", views.task_list, name="task_list"),
    path("today/", views.today_view, name="today"),

    path("block/add/", views.block_quick_add, name="block_quick_add"),
    path("responsible/add/", views.responsible_quick_add, name="responsible_quick_add"),

    path("debts/", views.debts_view, name="debts"),
    path("debts/add/", views.debt_add, name="debt_add"),
    path("debts/<int:pk>/update/", views.debt_update, name="debt_update"),
    path("debts/<int:pk>/delete/", views.debt_delete, name="debt_delete"),

    path("finance/", views.finance_page, name="finance"),
    path("payments/add/", views.payment_add, name="payment_add"),
    path("payments/<int:pk>/update/", views.payment_update, name="payment_update"),
    path("payments/<int:pk>/delete/", views.payment_delete, name="payment_delete"),
    path("payments/<int:pk>/history/", views.payment_history, name="payment_history"),
    path("payments/<int:pk>/records/add/", views.payment_record_add, name="payment_record_add"),
    path("payments/records/<int:pk>/delete/", views.payment_record_delete, name="payment_record_delete"),
    path("funds/add/", views.fund_add, name="fund_add"),
    path("funds/<int:pk>/update/", views.fund_update, name="fund_update"),
    path("funds/<int:pk>/delete/", views.fund_delete, name="fund_delete"),

    path("structure/", views.structure, name="structure"),
]
