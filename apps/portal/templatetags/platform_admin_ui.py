"""تگ‌هایِ رابطِ پنلِ مالکِ پلتفرم (فقط در قالب‌هایِ platform_admin بارگذاری می‌شوند)."""

from django import template

from apps.portal.platform_admin_nav import build_nav

register = template.Library()


@register.inclusion_tag("portal/platform_admin/_sidebar.html", takes_context=True)
def pa_sidebar(context):
    request = context.get("request")
    match = getattr(request, "resolver_match", None)
    return {"nav": build_nav(match.url_name if match else ""), "request": request}


@register.simple_tag(takes_context=True)
def pa_breadcrumb(context):
    request = context.get("request")
    match = getattr(request, "resolver_match", None)
    return build_nav(match.url_name if match else "")["breadcrumb"]
