from datetime import timedelta

from django import template
from django.utils import timezone

register = template.Library()


@register.filter(name="wall_clock")
def wall_clock(value):
    if value is None:
        return ""
    shifted = value + timedelta(hours=8)
    local = timezone.localtime(shifted)
    return local.strftime("%Y-%m-%d %H:%M")
