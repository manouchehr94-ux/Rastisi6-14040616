from apps.notifications import inbox_views


def inbox_bell(request):
    """``nt_bell`` برایِ زنگِ Header — فقط روی صفحه‌هایِ پنلِ فروشگاه/پلتفرم و فقط برایِ کاربرِ مجاز (یک Query برایِ شمارنده)."""
    match = getattr(request, "resolver_match", None)
    namespace = getattr(match, "namespace", "") if match else ""
    if namespace == "dashboard":
        return inbox_views.bell_context(request, inbox_views.DASH)
    if namespace == "portal_platform_admin":
        return inbox_views.bell_context(request, inbox_views.PLAT)
    return {}
