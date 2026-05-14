from django import template
from django.utils import timezone
from django.utils import formats
import re

register = template.Library()


@register.filter
def get_item(dictionary, key):
    if isinstance(dictionary, dict):
        return dictionary.get(key)
    return None


def _format_ar_number(value, singular, dual, plural_3_10, singular_11_plus):
    if value == 1:
        return singular
    if value == 2:
        return dual
    if 3 <= value <= 10:
        return f"{value} {plural_3_10}"
    return f"{value} {singular_11_plus}"


@register.filter
def arabic_timesince(value):
    """Return Arabic relative time using fixed threshold rules."""
    if not value:
        return "—"

    now = timezone.now()
    delta = now - value if now >= value else value - now
    total_seconds = int(delta.total_seconds())

    if total_seconds < 60:
        return "منذ ثوانٍ قليلة"

    minutes = total_seconds // 60
    if minutes < 60:
        return f"منذ {_format_ar_number(minutes, 'دقيقة', 'دقيقتين', 'دقائق', 'دقيقة')}"

    hours = minutes // 60
    if hours < 24:
        return f"منذ {_format_ar_number(hours, 'ساعة', 'ساعتين', 'ساعات', 'ساعة')}"

    days = hours // 24
    if days < 30:
        return f"منذ {_format_ar_number(days, 'يوم', 'يومين', 'أيام', 'يوماً')}"

    months = days // 30
    if months < 12:
        return f"منذ {_format_ar_number(months, 'شهر', 'شهرين', 'أشهر', 'شهراً')}"

    local_value = timezone.localtime(value)
    return f"منذ {formats.date_format(local_value, 'Y/m/d')}"


def _ar_meridiem(hour):
    return "ص" if hour < 12 else "م"


@register.filter
def ar_time12(value):
    if not value:
        return "—"
    local_value = timezone.localtime(value)
    hour_12 = local_value.hour % 12 or 12
    return f"{hour_12}:{local_value.minute:02d} {_ar_meridiem(local_value.hour)}"


@register.filter
def ar_datetime12(value):
    if not value:
        return "—"
    local_value = timezone.localtime(value)
    hour_12 = local_value.hour % 12 or 12
    return f"{formats.date_format(local_value, 'Y/m/d')} {hour_12}:{local_value.minute:02d} {_ar_meridiem(local_value.hour)}"


@register.filter
def keywords_to_list(value):
    if not value:
        return []
    parts = re.split(r"[،,;|]+", str(value))
    return [p.strip() for p in parts if p and p.strip()]


@register.filter
def star_rating(value, max_stars=5):
    try:
        score = int(value or 0)
        limit = int(max_stars or 5)
    except (TypeError, ValueError):
        return "—"
    score = max(0, min(score, limit))
    return ("★" * score) + ("☆" * (limit - score))
