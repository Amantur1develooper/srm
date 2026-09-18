from django.test import TestCase

from apps.crm.models import User

from .models import Decision, Entry, Meeting, Node, Section, Task


class FinsovetCoreTests(TestCase):
    def setUp(self):
        self.section = Section.objects.create(name="Производство", slug="production", order=0)
        self.root = Node.objects.create(section=self.section, name="Ала-Тоо")
        self.work = Node.objects.create(section=self.section, parent=self.root, name="Лифт")
        self.admin = User.objects.create_user("boss", password="x", role="admin")
        self.member = User.objects.create_user("marat", password="x", role="manager", can_access_finsovet=True)
        self.outsider = User.objects.create_user("nobody", password="x", role="manager")

    def test_current_state_is_latest_entry_rest_is_history(self):
        Entry.objects.create(node=self.work, kind=Entry.Kind.STATE, text="Переделка началась", author=self.member)
        self.assertEqual(self.work.current_state_text, "Переделка началась")
        Entry.objects.create(node=self.work, kind=Entry.Kind.STATE, text="Переделка закончена", author=self.member)
        self.work = Node.objects.get(pk=self.work.pk)
        self.assertEqual(self.work.current_state_text, "Переделка закончена")
        self.assertEqual(self.work.entries.count(), 2)  # старая запись никуда не делась

    def test_problem_flag_and_resolution(self):
        Entry.objects.create(node=self.work, kind=Entry.Kind.PROBLEM, text="Лифт повреждён")
        self.assertTrue(self.work.has_open_problem)
        Entry.objects.create(node=self.work, kind=Entry.Kind.STATE, text="Переделка началась")
        self.assertFalse(self.work.has_open_problem)  # обычное обновление снимает флаг

    def test_comment_does_not_override_current_state(self):
        Entry.objects.create(node=self.work, kind=Entry.Kind.STATE, text="Работа начата")
        Entry.objects.create(node=self.work, kind=Entry.Kind.COMMENT, text="Специалист будет завтра")
        self.assertEqual(self.work.current_state_text, "Работа начата")

    def test_access_denied_without_flag(self):
        self.client.login(username="nobody", password="x")
        self.assertEqual(self.client.get("/finsovet/").status_code, 403)
        self.client.login(username="marat", password="x")
        self.assertEqual(self.client.get("/finsovet/").status_code, 200)
        self.client.login(username="boss", password="x")
        self.assertEqual(self.client.get("/finsovet/").status_code, 200)  # админ имеет доступ всегда

    def test_quick_add_and_row_visible_on_dashboard(self):
        self.client.login(username="boss", password="x")
        resp = self.client.post("/finsovet/entry/add/", {"node": self.work.id, "text": "Переделка началась", "reported_by": ""})
        self.assertEqual(resp.status_code, 302)
        self.work = Node.objects.get(pk=self.work.pk)
        self.assertEqual(self.work.current_state_text, "Переделка началась")
        resp = self.client.get("/finsovet/")
        self.assertContains(resp, "Лифт")
        self.assertContains(resp, "Переделка началась")

    def test_task_lifecycle_logs_history_and_shows_on_node(self):
        self.client.login(username="boss", password="x")
        self.client.post(f"/finsovet/node/{self.work.id}/task/", {"title": "Проверить лифт", "due_date": "2026-09-20"})
        task = Task.objects.get(title="Проверить лифт")
        self.assertEqual(self.work.open_task, task)
        self.client.post(f"/finsovet/tasks/{task.id}/inline/", {"field": "due_date", "value": "2026-09-22"})
        task.refresh_from_db()
        self.assertEqual(str(task.due_date), "2026-09-22")
        self.assertTrue(task.events.filter(text__icontains="Срок изменён").exists())
        self.client.post(f"/finsovet/tasks/{task.id}/status/", {"status": "done"})
        task.refresh_from_db()
        self.assertEqual(task.status, Task.Status.DONE)
        self.assertTrue(task.events.filter(text__icontains="Статус").exists())

    def test_protocol_generation_scopes_by_meeting(self):
        self.client.login(username="boss", password="x")
        Entry.objects.create(node=self.work, kind=Entry.Kind.STATE, text="До заседания")
        meeting1 = Meeting.objects.create()
        Entry.objects.create(node=self.work, kind=Entry.Kind.STATE, text="После заседания")
        resp = self.client.get(f"/finsovet/protocol/{meeting1.id}/")
        self.assertContains(resp, "До заседания")
        self.assertNotContains(resp, "После заседания")

    def test_chat_message_posts_to_child_and_shows_in_object_feed(self):
        self.client.login(username="boss", password="x")
        resp = self.client.post("/finsovet/message/add/", {"node_id": self.work.id, "text": "Из чата про лифт"})
        self.assertRedirects(resp, f"/finsovet/?object={self.root.id}")
        entry = Entry.objects.get(text="Из чата про лифт")
        self.assertEqual(entry.kind, Entry.Kind.COMMENT)
        self.assertEqual(entry.author, self.admin)
        self.assertIn(self.work.id, self.root.descendant_ids())
        page = self.client.get(f"/finsovet/?object={self.root.id}")
        self.assertContains(page, "Из чата про лифт")

    def test_chat_badge_counts_open_tasks_and_problems(self):
        self.client.login(username="boss", password="x")
        self.assertEqual(self.root.open_tasks_count, 0)
        Task.objects.create(node=self.work, title="Проверить")
        self.assertEqual(self.root.open_tasks_count, 1)
        Entry.objects.create(node=self.work, kind=Entry.Kind.PROBLEM, text="Сломалось")
        self.assertEqual(self.root.open_problems_count, 1)
        page = self.client.get("/finsovet/")
        self.assertContains(page, "wa-badge red")  # проблема есть -> бейдж красный

    def test_decision_saved_with_node(self):
        self.client.login(username="boss", password="x")
        resp = self.client.post(
            "/finsovet/decisions/add/", {"text": "Переделать лифт", "node_id": self.work.id, "due_date": "2026-09-20"}
        )
        self.assertEqual(resp.status_code, 302)
        d = Decision.objects.get(text="Переделать лифт")
        self.assertEqual(d.node, self.work)
        self.assertEqual(d.section, self.section)
