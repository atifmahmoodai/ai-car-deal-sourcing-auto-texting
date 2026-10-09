from decimal import Decimal, InvalidOperation
from django import template

register = template.Library()


@register.filter
def cents(value):
    try:
        return f"{Decimal(value) / 100:,.2f}"
    except (TypeError, ValueError, InvalidOperation):
        return "—"
