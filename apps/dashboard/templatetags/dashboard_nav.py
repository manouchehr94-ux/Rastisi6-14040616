"""Template tags that render the merchant-admin navigation.

All three tags read the same permission-filtered model built by
``apps.dashboard.navigation.build_navigation`` — the sidebar, the section tab
bar and the command-palette index are therefore always consistent.
"""

from django import template

from apps.dashboard import navigation

register = template.Library()

_CACHE_KEY = "dashboard_navigation"


def _navigation(context):
    cache = context.render_context
    if _CACHE_KEY in cache:
        return cache[_CACHE_KEY]
    flat = context.flatten()
    flags = {key: value for key, value in flat.items() if key.startswith("can_")}
    request = flat.get("request")
    match = getattr(request, "resolver_match", None)
    nav = navigation.build_navigation(
        flags=flags,
        url_name=getattr(match, "url_name", "") or "",
        get=getattr(request, "GET", None),
        active_page=flat.get("active_page") or "",
        counts={
            "nav_pending_order_count": flat.get("nav_pending_order_count"),
            "nav_product_count": flat.get("nav_product_count"),
        },
    )
    cache[_CACHE_KEY] = nav
    return nav


@register.inclusion_tag("dashboard/partials/_admin_sidebar_nav.html", takes_context=True)
def admin_sidebar_nav(context):
    return {"nav": _navigation(context)}


@register.inclusion_tag("dashboard/partials/_admin_section_tabs.html", takes_context=True)
def admin_section_tabs(context):
    return {"nav": _navigation(context)}


@register.inclusion_tag("dashboard/partials/_admin_command_index.html", takes_context=True)
def admin_command_index(context):
    flat = context.flatten()
    flags = {key: value for key, value in flat.items() if key.startswith("can_")}
    return {"items": navigation.build_palette(flags)}
