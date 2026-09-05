"""Вспомогательные функции: телефоны, шаблоны сообщений, история."""
from __future__ import annotations

import re

from django.conf import settings


def normalize_phone(raw: str | int | None) -> str:
    """Приводит номер к международному виду без «+» для ссылок wa.me.

    Логика ориентирована на Кыргызстан:
      - 9 цифр (772281814)      -> 996772281814
      - 0XXXXXXXXX (10 цифр)    -> 996XXXXXXXXX
      - 996XXXXXXXXX            -> как есть
      - +7..., 7..., 8... и пр. -> оставляем цифры, 8->7 для РФ-номеров (11 цифр)
    """
    if raw is None:
        return ""
    digits = re.sub(r"\D", "", str(raw))
    if not digits:
        return ""
    cc = getattr(settings, "WHATSAPP_DEFAULT_COUNTRY_CODE", "996")

    if digits.startswith("00"):
        digits = digits[2:]
    if digits.startswith(cc):
        return digits
    if len(digits) == 9:
        return cc + digits
    if len(digits) == 10 and digits.startswith("0"):
        return cc + digits[1:]
    if len(digits) == 11 and digits.startswith("8"):
        return "7" + digits[1:]
    if len(digits) == 11 and digits.startswith("7"):
        return digits
    return digits


def phone_display(raw: str | int | None) -> str:
    n = normalize_phone(raw)
    if len(n) == 12 and n.startswith("996"):
        return f"+{n[:3]} {n[3:6]} {n[6:8]} {n[8:10]} {n[10:]}"
    return f"+{n}" if n else ""


TEMPLATE_VAR_RE = re.compile(r"\{([a-zA-Zа-яА-ЯёЁ_]+)\}")

# Синонимы переменных -> ключ значения
_VAR_ALIASES = {
    "имя": "name",
    "name": "name",
    "клиент": "name",
    "фио": "name",
    "телефон": "phone",
    "phone": "phone",
    "менеджер": "manager",
    "manager": "manager",
    "объект": "object",
    "object": "object",
    "что_ищет": "object",
    "бюджет": "budget",
    "budget": "budget",
    "следующий_шаг": "next_step",
    "next_step": "next_step",
}


def client_template_context(client) -> dict:
    first_name = (client.full_name or "").strip().split(" ")[0] if client.full_name else ""
    return {
        "name": first_name or client.full_name or "",
        "phone": phone_display(client.phone),
        "manager": client.manager.display_name if client.manager else "",
        "object": (client.looking_for or "").strip(),
        "budget": client.budget or "",
        "next_step": client.next_step or "",
    }


def render_template(body: str, client) -> str:
    ctx = client_template_context(client)

    def repl(match: re.Match) -> str:
        raw_key = match.group(1).strip().lower()
        key = _VAR_ALIASES.get(raw_key)
        if key is None:
            return match.group(0)
        return str(ctx.get(key, "")) or match.group(0)

    return TEMPLATE_VAR_RE.sub(repl, body or "")


def log_history(client, kind, text, user=None):
    from .models import ClientHistory

    return ClientHistory.objects.create(client=client, kind=kind, text=text, user=user)


def notify(user, kind, text, url=""):
    from .models import Notification

    if user is None:
        return None
    return Notification.objects.create(user=user, kind=kind, text=text, url=url)


RU_MONTHS = {
    "январ": 1, "феврал": 2, "март": 3, "апрел": 4, "ма": 5, "май": 5, "июн": 6,
    "июл": 7, "август": 8, "сентябр": 9, "октябр": 10, "ноябр": 11, "декабр": 12,
}


def parse_ru_date(value, year: int | None = None):
    """Парсит даты вида «15 января», «3 сентября», ISO-строки и date/datetime.

    Возвращает datetime.date или None.
    """
    import datetime as dt

    if value in (None, ""):
        return None
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    s = str(value).strip().lower()
    # ISO / dd.mm.yyyy
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d.%m.%y", "%d/%m/%Y"):
        try:
            return dt.datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    m = re.match(r"(\d{1,2})\s+([а-яё]+)", s)
    if m:
        day = int(m.group(1))
        mon_word = m.group(2)
        month = None
        for stem, num in RU_MONTHS.items():
            if mon_word.startswith(stem):
                month = num
                break
        if month:
            y = year or datetime_now_year()
            try:
                return dt.date(y, month, day)
            except ValueError:
                return None
    return None


def datetime_now_year() -> int:
    from django.utils import timezone

    return timezone.localdate().year


def parse_ru_datetime(value):
    """Как parse_ru_date, но сохраняет время суток, если оно было (выгрузки Bitrix
    отдают datetime целиком — «30.06.2026 11:10:04»). Возвращает aware datetime или None.
    """
    import datetime as dt

    from django.utils import timezone

    if value in (None, ""):
        return None
    if isinstance(value, dt.datetime):
        return timezone.make_aware(value) if timezone.is_naive(value) else value
    if isinstance(value, dt.date):
        return timezone.make_aware(dt.datetime.combine(value, dt.time.min))
    s = str(value).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M", "%d.%m.%Y"):
        try:
            return timezone.make_aware(dt.datetime.strptime(s, fmt))
        except ValueError:
            pass
    d = parse_ru_date(value)
    if d:
        return timezone.make_aware(dt.datetime.combine(d, dt.time.min))
    return None
