from django.test import TestCase
from django.utils import timezone

from apps.crm.models import User

from .models import Block, Entry, ExpectedFund, Payment, Question


class FinsovetCoreTests(TestCase):
    def setUp(self):
        self.block = Block.objects.create(name="К Блок", slug="k-blok", order=0)
        self.admin = User.objects.create_user("boss", password="x", role="admin")
        self.member = User.objects.create_user(
            "marat", password="x", role="manager", can_access_finsovet=True, is_finsovet_responsible=True,
        )
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
        def table(resp):
            # фильтр касается таблицы; боковые панели показывают всё
            html = resp.content.decode()
            return html[html.index('id="fsTable"'):html.index('class="fs-side"')]

        resp = self.client.get("/finsovet/", {"block": "k-blok"})
        self.assertIn("Лифты", table(resp))
        self.assertNotIn("Электричество", table(resp))
        resp2 = self.client.get("/finsovet/", {"status": "in_progress"})
        self.assertIn("Электричество", table(resp2))
        self.assertNotIn("Лифты", table(resp2))

    def test_reorder_single_and_group(self):
        self.client.login(username="boss", password="x")
        q2 = Question.objects.create(block=self.block, title="Второй", order=1)
        q3 = Question.objects.create(block=self.block, title="Третий", order=2)
        self.question.order = 0
        self.question.save(update_fields=["order"])
        # перетаскиваем «Второй» и «Третий» группой и бросаем перед «Лифты»
        resp = self.client.post(
            "/finsovet/question/reorder/", {"ids[]": [q2.id, q3.id], "target_id": self.question.id},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(resp.status_code, 200)
        ordered = list(Question.objects.filter(block=self.block).order_by("order").values_list("title", flat=True))
        self.assertEqual(ordered, ["Второй", "Третий", "Лифты"])

        # перетаскиваем «Лифты» (теперь последний) в начало — одной строкой, без target_id
        resp2 = self.client.post(
            "/finsovet/question/reorder/", {"ids[]": [self.question.id]},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(resp2.status_code, 200)
        ordered2 = list(Question.objects.filter(block=self.block).order_by("order").values_list("title", flat=True))
        self.assertEqual(ordered2, ["Лифты", "Второй", "Третий"])

    def test_block_and_responsible_quick_add(self):
        self.client.login(username="boss", password="x")
        resp = self.client.post(
            "/finsovet/block/add/", {"name": "Паркинг"}, HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["ok"])
        self.assertTrue(Block.objects.filter(name="Паркинг").exists())

        resp2 = self.client.post(
            "/finsovet/responsible/add/", {"name": "Новый Человек"}, HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(resp2.status_code, 200)
        self.assertTrue(resp2.json()["ok"])
        new_person = User.objects.get(first_name="Новый Человек")
        self.assertTrue(new_person.is_finsovet_responsible)
        from .access import responsible_people
        self.assertIn(new_person, responsible_people())

    def test_block_color_and_text_color(self):
        orange = Block.objects.create(name="К Блок 2", slug="k-blok-2", color="#f97316")
        beige = Block.objects.create(name="Ала Тоо 2", slug="ala-too-2", color="#e8dcc8")
        self.assertEqual(orange.text_color, "#fff")
        self.assertEqual(beige.text_color, "#1c1c1e")  # светлый фон -> тёмный текст


class FinancePanelTests(TestCase):
    """Панель «Финансы»: план выплат + ожидаемые средства, правка как в Excel."""

    def setUp(self):
        self.admin = User.objects.create_user("boss", password="x", role="admin")
        self.outsider = User.objects.create_user("nobody", password="x", role="manager")
        self.client.login(username="boss", password="x")

    def _add_payment(self):
        resp = self.client.post("/finsovet/payments/add/")
        self.assertEqual(resp.status_code, 200)
        return Payment.objects.get(pk=resp.json()["id"])

    def test_dashboard_shows_panels(self):
        resp = self.client.get("/finsovet/")
        for label in ("Финансы", "План выплат", "Ожидаемые средства", "Управление"):
            self.assertContains(resp, label)

    def test_finance_page_totals_and_nav(self):
        a = self._add_payment()
        b = self._add_payment()
        self.client.post(f"/finsovet/payments/{a.pk}/update/", {"field": "total", "value": "1000000"})
        self.client.post(f"/finsovet/payments/{b.pk}/update/", {"field": "total", "value": "139000"})
        self.client.post(f"/finsovet/payments/{b.pk}/records/add/", {"amount": "39000"})
        resp = self.client.get("/finsovet/finance/")
        self.assertContains(resp, "Ожидаемые средства")
        self.assertEqual(resp.context["pay_sum"]["total"], 1139000)
        self.assertEqual(resp.context["pay_sum"]["remaining"], 1100000)
        self.assertContains(resp, "1 139 000")
        self.assertContains(resp, 'href="/finsovet/finance/"')  # пункт в меню слева

    def test_add_row_on_top_or_end(self):
        first = self._add_payment()
        top = self._add_payment()  # «+ строка» — сверху, под «Итого»
        end = Payment.objects.get(pk=self.client.post("/finsovet/payments/add/", {"position": "end"}).json()["id"])
        self.assertEqual(list(Payment.objects.values_list("pk", flat=True)), [top.pk, first.pk, end.pk])

    def test_excel_like_edit_and_remaining(self):
        p = self._add_payment()
        url = f"/finsovet/payments/{p.pk}/update/"
        self.client.post(url, {"field": "name", "value": "Строй партнер и Ко Тимур"})
        d = self.client.post(url, {"field": "total", "value": "1 845 000"}).json()
        self.assertEqual(d["remaining"], "1 845 000")
        self.assertEqual(self.client.post(url, {"field": "total", "value": "1 845 000,5"}).json()["total"], "1 845 000,50")
        self.client.post(url, {"field": "total", "value": "1845000"})
        # «Оплачено» вписано прямо в ячейку → разница становится выплатой с датой
        d = self.client.post(url, {"field": "paid", "value": "500 000"}).json()
        self.assertEqual(d["paid"], "500 000")
        self.assertEqual(d["remaining"], "1 345 000")
        self.assertFalse(d["done"])
        self.assertEqual(p.records.count(), 1)
        bad = self.client.post(url, {"field": "total", "value": "много"})
        self.assertEqual(bad.status_code, 400)

    def test_add_and_delete_record_marks_done(self):
        p = self._add_payment()
        self.client.post(f"/finsovet/payments/{p.pk}/update/", {"field": "total", "value": "139000"})
        d = self.client.post(f"/finsovet/payments/{p.pk}/records/add/", {"amount": "139 000", "date": "2026-10-01"}).json()
        self.assertTrue(d["done"])  # полностью оплачено → строка зачёркнута
        hist = self.client.get(f"/finsovet/payments/{p.pk}/history/").json()
        self.assertEqual(hist["records"][0]["date"], "01.10.2026")
        d = self.client.post(hist["records"][0]["delete_url"]).json()
        self.assertFalse(d["done"])
        self.assertEqual(d["remaining"], "139 000")

    def test_delete_row_hides_it_but_keeps_history(self):
        p = self._add_payment()
        self.client.post(f"/finsovet/payments/{p.pk}/records/add/", {"amount": "10"})
        self.client.post(f"/finsovet/payments/{p.pk}/delete/")
        p.refresh_from_db()
        self.assertFalse(p.is_active)
        self.assertEqual(p.records.count(), 1)

    def test_expected_funds_crud(self):
        resp = self.client.post("/finsovet/funds/add/").json()
        url = f"/finsovet/funds/{resp['id']}/update/"
        self.client.post(url, {"field": "source", "value": "Продажа квартир"})
        self.assertEqual(self.client.post(url, {"field": "amount", "value": "2500000"}).json()["amount"], "2 500 000")
        f = ExpectedFund.objects.get(pk=resp["id"])
        self.assertEqual(f.source, "Продажа квартир")
        self.client.post(f"/finsovet/funds/{f.pk}/delete/")
        f.refresh_from_db()
        self.assertFalse(f.is_active)

    def test_outsider_cannot_touch_finance(self):
        self.client.login(username="nobody", password="x")
        self.assertEqual(self.client.post("/finsovet/payments/add/").status_code, 403)
        self.assertEqual(self.client.post("/finsovet/funds/add/").status_code, 403)
