from django.contrib.auth import get_user_model
from django.test import TestCase

from .models import Client, Message, Stage, Task
from .services import excel_import
from .utils import normalize_phone, parse_ru_date, render_template

User = get_user_model()


class PhoneTests(TestCase):
    def test_normalize(self):
        self.assertEqual(normalize_phone(772281814), "996772281814")
        self.assertEqual(normalize_phone("0772 28 18 14"), "996772281814")
        self.assertEqual(normalize_phone("+996 772 281814"), "996772281814")
        self.assertEqual(normalize_phone("8 701 1234567"), "77011234567")
        self.assertEqual(normalize_phone(""), "")
        self.assertEqual(normalize_phone(None), "")


class DateTests(TestCase):
    def test_ru_dates(self):
        self.assertEqual(parse_ru_date("15 января", 2026).isoformat(), "2026-01-15")
        self.assertEqual(parse_ru_date("3 сентября", 2026).isoformat(), "2026-09-03")
        self.assertEqual(parse_ru_date("2026-05-30").isoformat(), "2026-05-30")
        self.assertIsNone(parse_ru_date("каждый месяц"))


class TemplateRenderTests(TestCase):
    def setUp(self):
        self.stage = Stage.objects.create(name="Новая", slug="new", order=1)
        self.mgr = User.objects.create_user("m1", first_name="Амантур", role="manager")

    def test_render(self):
        c = Client.objects.create(
            full_name="Азамат Осмонов", phone="0772281814", stage=self.stage,
            manager=self.mgr, looking_for="1-к квартира", budget="50% наличными",
        )
        out = render_template("Здравствуйте, {имя}! Ищете {объект}? — {менеджер}", c)
        self.assertEqual(out, "Здравствуйте, Азамат! Ищете 1-к квартира? — Амантур")


class ImportTests(TestCase):
    def setUp(self):
        for slug, name in [("new", "Новая заявка"), ("hot", "Горячий"), ("won", "Сделка")]:
            Stage.objects.create(name=name, slug=slug, order=1)

    def _wb_bytes(self):
        from io import BytesIO

        from openpyxl import Workbook

        wb = Workbook()
        ws = wb.active
        ws.title = "список"
        ws.append([None, "фио", "контакт", "дата обращения", "стадии", "что ищет", "следующий шаг", "срок задачи"])
        ws.append([1, "Азамат", 772281814, "15 января", "новая", "1к Эко Парк", "пригласить", "3 сентября"])
        ws.append([2, "Саид", 555000111, "5 июня", "горячий", "помещение", "греть", None])
        buf = BytesIO()
        wb.save(buf)
        return buf.getvalue()

    def test_preview_and_import(self):
        raw = self._wb_bytes()
        previews = excel_import.preview_workbook(raw)
        self.assertEqual(previews[0].total_rows, 2)
        self.assertIn("full_name", previews[0].suggested_mapping)

        res = excel_import.run_import(
            file_bytes=raw, filename="t.xlsx", sheet_name="список",
            header_row=previews[0].header_row, mapping=previews[0].suggested_mapping,
            duplicate_strategy="skip",
        )
        self.assertEqual(res.created, 2)
        self.assertEqual(Client.objects.get(full_name="Азамат").phone_normalized, "996772281814")
        # авто-задача из "следующий шаг" + "срок задачи"
        self.assertTrue(Task.objects.filter(title="пригласить").exists())

        # повторный импорт со skip — дублей нет
        res2 = excel_import.run_import(
            file_bytes=raw, filename="t.xlsx", sheet_name="список",
            header_row=previews[0].header_row, mapping=previews[0].suggested_mapping,
            duplicate_strategy="skip",
        )
        self.assertEqual(res2.created, 0)
        self.assertEqual(res2.skipped, 2)


class AccessTests(TestCase):
    def setUp(self):
        self.stage = Stage.objects.create(name="Новая", slug="new", order=1)
        self.m1 = User.objects.create_user("m1", password="x", role="manager")
        self.m2 = User.objects.create_user("m2", password="x", role="manager")
        self.c1 = Client.objects.create(full_name="К1", stage=self.stage, manager=self.m1)
        self.c2 = Client.objects.create(full_name="К2", stage=self.stage, manager=self.m2)

    def test_manager_sees_only_own(self):
        self.client.login(username="m1", password="x")
        resp = self.client.get("/clients/")
        self.assertContains(resp, "К1")
        self.assertNotContains(resp, ">К2<")
        # чужой клиент недоступен (404 — не раскрываем существование)
        self.assertEqual(self.client.get(f"/clients/{self.c2.id}/").status_code, 404)

    def test_stage_change_logs_history(self):
        self.client.login(username="m1", password="x")
        hot = Stage.objects.create(name="Горячий", slug="hot", order=2)
        self.client.post(f"/clients/{self.c1.id}/stage/", {"stage": hot.id})
        self.c1.refresh_from_db()
        self.assertEqual(self.c1.stage_id, hot.id)
        self.assertTrue(self.c1.history.filter(kind="stage").exists())
        self.assertTrue(self.c1.tasks.filter(title="Связаться с клиентом").exists())

    def test_bulk_delete(self):
        self.client.login(username="m1", password="x")
        self.client.post("/clients/bulk/", {"client_ids": [self.c1.id], "action": "delete"})
        self.assertFalse(Client.objects.filter(pk=self.c1.id).exists())

    def test_inline_update(self):
        self.client.login(username="m1", password="x")
        resp = self.client.post(
            f"/clients/{self.c1.id}/inline/", {"field": "phone", "value": "0700111222"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(resp.status_code, 200)
        self.c1.refresh_from_db()
        self.assertEqual(self.c1.phone, "0700111222")
        # чужого клиента править нельзя
        resp = self.client.post(
            f"/clients/{self.c2.id}/inline/", {"field": "phone", "value": "x"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(resp.status_code, 404)

    def test_quick_create_in_kanban(self):
        self.client.login(username="m1", password="x")
        resp = self.client.post(
            "/kanban/quick-add/", {"stage": self.stage.id, "full_name": "Новый Лид", "phone": "0700"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(Client.objects.filter(full_name="Новый Лид", manager=self.m1).exists())


class ClientFormTests(TestCase):
    def setUp(self):
        self.stage = Stage.objects.create(name="Новая", slug="new", order=1)

    def test_requires_name_on_create(self):
        from .forms import ClientForm

        form = ClientForm(data={"last_name": "", "first_name": "", "phone": "123"})
        self.assertFalse(form.is_valid())
        self.assertIn("last_name", form.errors)

    def test_legacy_client_editable_without_name_parts(self):
        from .forms import ClientForm

        legacy = Client.objects.create(full_name="Одной строкой ФИО", stage=self.stage)
        form = ClientForm(data={"last_name": "", "first_name": "", "phone": "555"}, instance=legacy)
        self.assertTrue(form.is_valid(), form.errors)
        obj = form.save(commit=False)
        self.assertEqual(obj.full_name, "Одной строкой ФИО")  # не затёрлось

    def test_compose_full_name_from_parts(self):
        c = Client.objects.create(last_name="Осмонов", first_name="Азамат", stage=self.stage)
        self.assertEqual(c.full_name, "Осмонов Азамат")
