from django import template
from django.utils import timezone

register = template.Library()


@register.filter(name="wall_clock")
def wall_clock(value):
    """统一展示口径：把 aware 时刻按 settings.TIME_ZONE (Asia/Shanghai)
    渲染为本地墙钟。入库一律存 UTC，禁止在此手挪小时偏移。"""
    if value is None:
        return ""
    return timezone.localtime(value).strftime("%Y-%m-%d %H:%M")
