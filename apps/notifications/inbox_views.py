"""صندوقِ اعلانِ مدیران — ویوهایِ مشترکِ «پنلِ فروشگاه» و «پنلِ پلتفرم» (یک پیاده‌سازی، دو محدوده).

هر درخواست فقط برایِ **خودِ کاربرِ احراز‌هویت‌شده** و **همین محدوده** کار می‌کند: شناسه‌ی اعلانِ دیگران/فروشگاهِ دیگر ⇒ 404 (حدس‌زدنی/خواندنی نیست)؛ لینکِ اعلان از نامِ مسیر ساخته
می‌شود و مجوزِ صفحه‌ی مقصد دوباره بررسی می‌شود؛ همه‌ی POSTها CSRF دارند؛ ثبت/لغوِ Subscription و اعلانِ آزمایشی rate-limit دارند."""

from __future__ import annotations

import json
import uuid
from functools import wraps
from types import SimpleNamespace

from django.contrib import messages
from django.core.paginator import Paginator
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from apps.core.services.rate_limit import RateLimitExceeded, RateLimitUnavailable, enforce_rate_limit
from apps.notifications import registry as R
from apps.notifications.models import NotificationPreference, Severity, WebPushSubscription
from apps.notifications.services import inbox_engine as eng
from apps.notifications.services import inbox_service as svc
from apps.notifications.services import scope as S
from apps.notifications.services import webpush

DASH = SimpleNamespace(name="dashboard", ns="dashboard", base="dashboard/base_admin.html", platform=False)
PLAT = SimpleNamespace(name="platform", ns="portal_platform_admin", base="portal/platform_admin/base.html", platform=True)


def _wants_json(request) -> bool:
    return request.headers.get("x-requested-with") == "XMLHttpRequest" or "application/json" in request.headers.get("accept", "")


def _ctx(request, site):
    return SimpleNamespace(site=site, user=request.user, store=None if site.platform else request.store, scope_key=S.key_for(None if site.platform else request.store))


def _guard(site):
    """دکوراتورِ دسترسی: پنلِ فروشگاه = ``staff_required`` (عضویتِ فعالِ همین فروشگاه)؛ پنلِ پلتفرم = staff + superuser (غیرِ آن 404)."""
    def deco(view):
        if not site.platform:
            from apps.dashboard.decorators import staff_required

            return staff_required(view)

        @wraps(view)
        def wrapper(request, *a, **kw):
            if not request.user.is_authenticated:
                return redirect(f"{reverse('portal_platform_admin:login')}")
            if not S.is_platform_staff(request.user):
                raise Http404
            return view(request, *a, **kw)
        return wrapper
    return deco


def _limited(request, name: str, max_attempts: int, window: int):
    try:
        enforce_rate_limit(name, str(request.user.pk), max_attempts=max_attempts, window_seconds=window)
    except RateLimitExceeded:
        return JsonResponse({"ok": False, "error": "rate_limited"}, status=429)
    except RateLimitUnavailable:
        return JsonResponse({"ok": False, "error": "unavailable"}, status=503)
    return None


def _url(c, name, **kw):
    return reverse(f"{c.site.ns}:{name}", kwargs=kw)


def _back(request, c):
    nxt = request.POST.get("next", "")
    if nxt and url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}, require_https=request.is_secure()) and nxt.startswith(_url(c, "inbox-home")):
        return redirect(nxt)
    return redirect(_url(c, "inbox-home"))


def bell_context(request, site) -> dict:
    """داده‌هایِ زنگ (برایِ context processor/تمپلیت‌هایِ پایه): فقط برایِ کاربرِ مجاز."""
    if not request.user.is_authenticated:
        return {}
    store = None if site.platform else getattr(request, "store", None)
    if not site.platform and (store is None or getattr(request, "store_membership", None) is None):
        return {}
    if site.platform and not S.is_platform_staff(request.user):
        return {}
    from django.conf import settings

    return {"nt_bell": {
        "summary_url": reverse(f"{site.ns}:inbox-summary"), "inbox_url": reverse(f"{site.ns}:inbox-home"), "prefs_url": reverse(f"{site.ns}:inbox-preferences"),
        "poll_seconds": max(15, int(getattr(settings, "RASTISI_NOTIF_POLL_SECONDS", 30))), "user_key": f"{request.user.pk}:{S.key_for(store)}",
        "unread": svc.unread_count(request.user, store, membership=getattr(request, "store_membership", None)), "ns": site.ns,
    }}


# ------------------------------------------------------------------------------------------------------------------------------------ factory
def build(site):
    guard = _guard(site)

    @guard
    @require_GET
    def inbox_page(request):
        c = _ctx(request, site)
        params = request.GET
        page = Paginator(svc.filtered(c.user, c.store, params), svc.PAGE_SIZE).get_page(params.get("page"))
        base_qs = "&".join(f"{k}={v}" for k, v in params.items() if k != "page" and v)
        allowed = {R.get_type(k).category for k in S.allowed_type_keys(c.user, c.store)}
        return render(request, "notifications/inbox.html", {
            "base_template": site.base, "site": site, "page": page, "items": [svc.serialize(i) | {"obj": i} for i in page], "params": params, "base_qs": base_qs,
            "categories": [(k, v) for k, v in R.CATEGORIES.items() if k in allowed], "unread": svc.unread_count(c.user, c.store),
            "views": [("", "فعال"), ("unread", "خوانده‌نشده"), ("pinned", "سنجاق‌شده"), ("snoozed", "به‌تعویق‌افتاده"), ("archived", "بایگانی")],
            "ranges": [("", "همه‌ی زمان‌ها"), ("1", "۲۴ ساعت اخیر"), ("7", "۷ روز اخیر"), ("30", "۳۰ روز اخیر"), ("90", "۹۰ روز اخیر")],
            "severities": [(str(v), l) for v, l in Severity.choices], "snoozes": [("1h", "یک ساعت"), ("4h", "چهار ساعت"), ("tomorrow", "تا فردا"), ("week", "یک هفته")],
            "active_nav": "notifications", "nt_urls": {"inbox": _url(c, "inbox-home"), "prefs": _url(c, "inbox-preferences"), "all_read": _url(c, "inbox-read-all")},
        })

    @guard
    @never_cache
    @require_GET
    def summary_api(request):
        c = _ctx(request, site)
        try:
            since = int(request.GET.get("since", "0"))
        except ValueError:
            since = 0
        data = svc.summary(c.user, c.store, since_ms=since)
        data["user_key"] = f"{c.user.pk}:{c.scope_key}"
        return JsonResponse(data)

    @guard
    @require_GET
    def detail_page(request, public_id):
        c = _ctx(request, site)
        item = svc.get_item(c.user, c.store, public_id)
        if item is None:
            raise Http404
        svc.mark(item, "read")
        link = svc.resolve_link(item.event, site.ns) if S.can_open_link(c.user, item.event) else ""
        return render(request, "notifications/detail.html", {
            "base_template": site.base, "site": site, "item": item, "event": item.event, "link": link, "severity_label": svc.SEVERITY_LABELS[item.event.severity],
            "tone": svc.SEVERITY_TONES[item.event.severity], "category_label": R.category_label(item.event.category), "inbox_url": _url(c, "inbox-home"),
            "go_url": _url(c, "inbox-go", public_id=item.public_id), "active_nav": "notifications",
        })

    @guard
    @require_POST
    def item_action(request, public_id, action):
        c = _ctx(request, site)
        item = svc.get_item(c.user, c.store, public_id)
        if item is None:
            return JsonResponse({"ok": False}, status=404) if _wants_json(request) else _404()
        ok = svc.mark(item, action, snooze=request.POST.get("snooze", ""))
        if _wants_json(request):
            return JsonResponse({"ok": ok, "unread": svc.unread_count(c.user, c.store)}, status=200 if ok else 400)
        if not ok:
            messages.error(request, "این عملیات معتبر نیست.")
        return _back(request, c)

    @guard
    @require_POST
    def all_read(request):
        c = _ctx(request, site)
        n = svc.mark_all_read(c.user, c.store)
        if _wants_json(request):
            return JsonResponse({"ok": True, "marked": n, "unread": 0})
        messages.success(request, f"{n} اعلان خوانده شد." if n else "اعلانِ خوانده‌نشده‌ای نبود.")
        return _back(request, c)

    @guard
    @require_GET
    def go(request, public_id):
        """خواندن + رفتن به موجودیت — فقط اگر مجوزِ صفحه‌ی مقصد را دارید؛ وگرنه به جزئیاتِ اعلان (نه Permission-bypass، نه open-redirect)."""
        c = _ctx(request, site)
        item = svc.get_item(c.user, c.store, public_id)
        if item is None:
            raise Http404
        svc.mark(item, "read")
        target = svc.resolve_link(item.event, site.ns) if S.can_open_link(c.user, item.event) else ""
        if not target:
            messages.info(request, "دسترسیِ لازم برای صفحه‌ی مرتبط را ندارید یا این صفحه دیگر وجود ندارد.")
            return redirect(_url(c, "inbox-detail", public_id=item.public_id))
        return redirect(target)

    @guard
    def preferences(request):
        c = _ctx(request, site)
        pref = svc.get_preference(c.user, c.store)
        allowed_types = [R.get_type(k) for k in S.allowed_type_keys(c.user, c.store)]
        categories = [(k, v, R.CATEGORY_HINTS.get(k, "")) for k, v in R.CATEGORIES.items() if any(t.category == k for t in allowed_types)]
        if request.method == "POST":
            pref.toast_enabled = request.POST.get("toast_enabled") == "1"
            pref.mute_low = request.POST.get("mute_low") == "1"
            pref.browser_enabled = request.POST.get("browser_enabled") == "1"
            for field in ("min_toast_severity", "min_browser_severity"):
                value = request.POST.get(field, "")
                if value.isdigit() and int(value) in (2, 3, 4):
                    setattr(pref, field, int(value))
            enabled = set(request.POST.getlist("categories"))
            pref.disabled_categories = [k for k, _v, _h in categories if k not in enabled and k not in R.ALWAYS_INBOX_CATEGORIES]
            pref.save()
            messages.success(request, "تنظیمات اعلان‌ها ذخیره شد.")
            return redirect(_url(c, "inbox-preferences"))
        devices = WebPushSubscription.objects.filter(user=c.user, scope_key=c.scope_key, revoked_at__isnull=True).order_by("-last_seen_at")
        from django.conf import settings

        return render(request, "notifications/preferences.html", {
            "base_template": site.base, "site": site, "pref": pref, "categories": categories, "disabled": set(pref.disabled_categories or []),
            "always": R.ALWAYS_INBOX_CATEGORIES, "devices": devices, "severities": [(v, l) for v, l in Severity.choices if v >= 2],
            "push": {"enabled": bool(getattr(settings, "RASTISI_NOTIF_WEBPUSH_ENABLED", False)), "configured": webpush.is_configured(), "public_key": webpush.public_key_b64u(),
                     "subscribe_url": _url(c, "inbox-push-subscribe"), "unsubscribe_url": _url(c, "inbox-push-unsubscribe"), "sw_url": _url(c, "inbox-sw")},
            "test_url": _url(c, "inbox-test"), "inbox_url": _url(c, "inbox-home"), "scope_label": "پلتفرم راستی‌سی" if site.platform else request.store.name,
            "active_nav": "notifications",
        })

    @guard
    @require_POST
    def push_subscribe(request):
        c = _ctx(request, site)
        if (resp := _limited(request, "nt_push_subscribe", 20, 3600)) is not None:
            return resp
        try:
            payload = json.loads(request.body or b"{}")
            sub = webpush.register(c.user, c.scope_key, payload, device_label=str(payload.get("label", ""))[:80], user_agent=request.headers.get("user-agent", ""))
        except (ValueError, webpush.SubscriptionError) as exc:
            return JsonResponse({"ok": False, "error": str(exc) if isinstance(exc, webpush.SubscriptionError) else "bad_request"}, status=400)
        return JsonResponse({"ok": True, "id": sub.pk})

    @guard
    @require_POST
    def push_unsubscribe(request):
        c = _ctx(request, site)
        endpoint, device = "", request.POST.get("device")
        if request.content_type == "application/json":
            try:
                endpoint = str(json.loads(request.body or b"{}").get("endpoint", ""))
            except ValueError:
                return JsonResponse({"ok": False}, status=400)
        n = webpush.unregister(c.user, endpoint, public_id=int(device) if device and device.isdigit() else None)
        if _wants_json(request) or request.content_type == "application/json":
            return JsonResponse({"ok": True, "revoked": n})
        messages.success(request, "دستگاه حذف شد." if n else "دستگاهی پیدا نشد.")
        return redirect(_url(c, "inbox-preferences"))

    @guard
    @require_POST
    def send_test(request):
        """اعلانِ آزمایشی — فقط برایِ خودِ درخواست‌دهنده؛ هیچ سرویسِ خارجی صدا زده نمی‌شود (Web Push هم فقط اگر پرچم+کلید فعال باشد)."""
        c = _ctx(request, site)
        if (resp := _limited(request, "nt_test", 10, 600)) is not None:
            return resp
        key = "platform.test" if site.platform else "system.test"
        eng.publish(key, store=c.store, title="اعلان آزمایشی", summary="اگر این پیام را می‌بینید، صندوق و اعلان فوری درست کار می‌کند.",
                    dedupe_key=f"test:{uuid.uuid4().hex}", only_users=[c.user], force_inbox=[c.user])
        if _wants_json(request):
            return JsonResponse({"ok": True})
        messages.success(request, "اعلان آزمایشی ارسال شد؛ باید در زنگ بالای صفحه دیده شود.")
        return redirect(_url(c, "inbox-preferences"))

    @guard
    @require_GET
    def service_worker(request):
        from django.contrib.staticfiles import finders

        path = finders.find("notifications/sw.js")
        if not path:
            raise Http404
        with open(path, encoding="utf-8") as fh:
            body = fh.read().replace("__SUMMARY_URL__", reverse(f"{site.ns}:inbox-summary")).replace("__INBOX_URL__", reverse(f"{site.ns}:inbox-home"))
        response = HttpResponse(body, content_type="application/javascript; charset=utf-8")
        response["Service-Worker-Allowed"] = "/admin-portal/" if not site.platform else "/"
        response["Cache-Control"] = "no-cache"
        return response

    return {
        "inbox-home": inbox_page, "inbox-summary": summary_api, "inbox-detail": detail_page, "inbox-action": item_action,
        "inbox-read-all": all_read, "inbox-go": go, "inbox-preferences": preferences, "inbox-push-subscribe": push_subscribe,
        "inbox-push-unsubscribe": push_unsubscribe, "inbox-test": send_test, "inbox-sw": service_worker,
    }


def _404():
    raise Http404


VIEWS_DASH = build(DASH)
VIEWS_PLAT = build(PLAT)


def url_patterns(views: dict):
    """نقشه‌ی مسیرها — پیشوند ``inbox/`` تا با ``notifications/<event_key>/``ِ قدیمیِ قالب‌ها برخورد نکند."""
    from django.urls import path

    v = views
    return [
        path("inbox/", v["inbox-home"], name="inbox-home"),
        path("inbox/api/summary/", v["inbox-summary"], name="inbox-summary"),
        path("inbox/read-all/", v["inbox-read-all"], name="inbox-read-all"),
        path("inbox/preferences/", v["inbox-preferences"], name="inbox-preferences"),
        path("inbox/push/subscribe/", v["inbox-push-subscribe"], name="inbox-push-subscribe"),
        path("inbox/push/unsubscribe/", v["inbox-push-unsubscribe"], name="inbox-push-unsubscribe"),
        path("inbox/test/", v["inbox-test"], name="inbox-test"),
        path("inbox/sw.js", v["inbox-sw"], name="inbox-sw"),
        path("inbox/<uuid:public_id>/", v["inbox-detail"], name="inbox-detail"),
        path("inbox/<uuid:public_id>/go/", v["inbox-go"], name="inbox-go"),
        path("inbox/<uuid:public_id>/<slug:action>/", v["inbox-action"], name="inbox-action"),
    ]
