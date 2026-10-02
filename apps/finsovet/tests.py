from django.test import TestCase
from django.utils import timezone

from apps.crm.models import User

from .models import Block, Entry, Question


class FinsovetCoreTests(TestCase):
    def setUp(self):
        self.block = Block.objects.create(name="К Блок", slug="k-blok", order=0)
        self.admin = User.objects.create_user("boss", password="x", role="admin")
        self.member = User.objects.create_user("marat", password="x", role="manager", can_access_finsovet=True)
        self.outsider = User.objects.create_user("nobody", password="x", role="manager")
        self.question = Question.objects.create(block=self.block, title="Лифты", created_by=self.admin)

    def test_access_denied_without_flag(self):
        self.client.login(username="nobody", password="x")
        self.assertEqual(self.client.get("/finsovet/").status_code, 403)
        self.client.login(username="marat", password="x")
        self.assertEqual(self.client.get("/finsovet/").status_code, 200)
        self.client.login(username="boss", password="x")
        self.assertEqual(self.client.get("/finsovet/").status_code, 200)

    def test_quick_add_minimal_fields(self):
        self.client.login(username="boss", password="x")
        resp = self.client.post("/finsovet/question/add/", {"block": self.block.id, "title": "Отопление"})
        self.assertEqual(resp.status_code, 302)
        q = Question.objects.get(title="Отопление")
        self.assertEqual(q.status, Question.Status.SOON)
        self.assertFalse(q.action)

    def test_inline_status_change_logs_history(self):
        self.client.login(username="boss", password="x")
        resp = self.client.post(
            f"/finsovet/question/{self.question.id}/inline/", {"field": "status", "value": "in_progress"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(resp.status_code, 200)
        self.question.refresh_from_db()
        self.assertEqual(self.question.status, Question.Status.IN_PROGRESS)
        self.assertTrue(self.question.entries.filter(kind=Entry.Kind.CHANGE, text__icontains="Статус").exists())

    def test_inline_action_due_responsible(self):
        self.client.login(username="boss", password="x")
        self.client.post(f"/finsovet/question/{self.question.id}/inline/", {"field": "action", "value": "Оплатить"})
        self.client.post(f"/finsovet/question/{self.question.id}/inline/", {"field": "due_date", "value": "2026-10-03"})
        self.client.post(f"/finsovet/question/{self.question.id}/inline/", {"field": "responsible", "value": self.member.id})
        self.question.refresh_from_db()
        self.assertEqual(self.question.action, "Оплатить")
        self.assertEqual(str(self.question.due_date), "2026-10-03")
        self.assertEqual(self.question.responsible, self.member)
        self.assertEqual(self.question.entries.filter(kind=Entry.Kind.CHANGE).count(), 3)

    def test_comment_auto_stamps_date_and_author(self):
        self.client.login(username="boss", password="x")
        resp = self.client.post(f"/finsovet/question/{self.question.id}/comment/", {"text": "Обшивка завершена"})
        self.assertEqual(resp.status_code, 302)
        entry = Entry.objects.get(question=self.question, text="Обшивка завершена")
        self.assertEqual(entry.kind, Entry.Kind.COMMENT)
        self.assertEqual(entry.author, self.admin)
        self.assertIsNotNone(entry.created_at)

    def test_task_list_is_filter_over_questions_with_action(self):
        self.client.login(username="boss", password="x")
        Question.objects.create(block=self.block, title="Без действия")
        with_action = Question.objects.create(block=self.block, title="Оплатить лифты", action="Оплатить", responsible=self.member)
        done_with_action = Question.objects.create(
            block=self.block, title="Готово", action="Сделать", status=Question.Status.DONE
        )
        resp = self.client.get("/finsovet/tasks/")
        self.assertContains(resp, "Оплатить лифты")
        self.assertNotContains(resp, "Без действия")
        self.assertNotContains(resp, "Готово")  # завершённые не висят в задачах
        resp2 = self.client.get("/finsovet/tasks/", {"responsible": self.member.id})
        self.assertContains(resp2, "Оплатить лифты")

    def test_today_shows_only_todays_entries(self):
        self.client.login(username="boss", password="x")
        Entry.objects.create(question=self.question, kind=Entry.Kind.COMMENT, text="Сегодняшняя запись", author=self.admin)
        old = Entry.objects.create(question=self.question, kind=Entry.Kind.COMMENT, text="Старая запись", author=self.admin)
        Entry.objects.filter(pk=old.pk).update(created_at=timezone.now() - timezone.timedelta(days=5))
        resp = self.client.get("/finsovet/today/")
        self.assertContains(resp, "Сегодняшняя запись")
        self.assertNotContains(resp, "Старая запись")

    def test_dashboard_filters_by_block_and_status(self):
        self.client.login(username="boss", password="x")
        other_block = Block.objects.create(name="ЖЗИ", slug="zhzi", order=1)
        Question.objects.create(block=other_block, title="Электричество", status=Question.Status.IN_PROGRESS)
        resp = self.client.get("/finsovet/", {"block": "k-blok"})
        self.assertContains(resp, "Лифты")
        self.assertNotContains(resp, "Электричество")
        resp2 = self.client.get("/finsovet/", {"status": "in_progress"})
        self.assertContains(resp2, "Электричество")
        self.assertNotContains(resp2, "Лифты")
