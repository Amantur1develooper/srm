from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()


def format_money(value) -> str:
    """3800000 → «3 800 000,00» — как в Excel-таблице финансов."""
    try:
        d = Decimal(value or 0).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError):
        return ""
    sign = "−" if d < 0 else ""
    whole, frac = f"{abs(d):.2f}".split(".")
    groups = []
    while whole:
        groups.insert(0, whole[-3:])
        whole = whole[:-3]
    return f"{sign}{' '.join(groups)},{frac}"


@register.filter
def money(value):
    return format_money(value)
