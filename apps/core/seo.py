"""SEOِ فروشگاهیِ tenant-safe (Checkpoint 6، ADR-90): sitemap و robots که
به Storeِ resolve‌شده از Hostِ درخواست محدودند — هرگز URLِ فروشگاهِ دیگر یا
کالای پیش‌نویس منتشر نمی‌کنند.

چون چارچوبِ ``django.contrib.sites`` نصب نیست، این‌ها به‌جای
``django.contrib.sitemaps`` (که به Site وابسته است) view‌هایِ سبکِ
request-scoped‌اند: دامنه‌یِ canonical همان Hostِ tenant است."""

from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.urls import reverse

from apps.catalog.models import Category
from apps.catalog.services.product_publish_service import storefront_listing_products
from apps.content.models import ContentPage
from apps.stores.resolution import resolve_store_for_storefront

from . import seo_policy

#: بیشینه‌ی URLهایِ هر بخش در sitemap — کرانه‌دار تا کاتالوگِ بزرگ سرریز نکند.
SITEMAP_LIMIT = 5000


def _abs(request, path: str, *, origin: str | None = None) -> str:
    """URLِ مطلق روی دامنه‌یِ canonical این Store (یا Hostِ درخواست اگر canonical تعریف نشده)."""
    return f"{origin}{path}" if origin else request.build_absolute_uri(path)


def _sitemap_entries(request, store, origin=None):
    """فهرستِ (loc, lastmod) برایِ محتوایِ عمومیِ این Store."""
    def link(path):                                            # every URL is built on the Store's canonical origin
        return _abs(request, path, origin=origin)

    entries = [{"loc": link(reverse("catalog:home")), "lastmod": None, "priority": "1.0"}]
    entries.append({"loc": link(reverse("catalog:product-list")), "lastmod": None, "priority": "0.8"})

    categories = (
        Category.objects.filter(store=store, is_active=True)
        .order_by("order", "name")[:SITEMAP_LIMIT]
    )
    for cat in categories:
        loc = link(reverse("catalog:product-list")) + f"?category={cat.slug}"
        entries.append({"loc": loc, "lastmod": cat.updated_at, "priority": "0.6"})

    products = (
        storefront_listing_products(store)
        .order_by("-updated_at")[:SITEMAP_LIMIT]
    )
    for product in products:
        loc = link(reverse("catalog:product-detail", args=[product.slug]))
        entries.append({"loc": loc, "lastmod": product.updated_at, "priority": "0.7"})

    pages = ContentPage.objects.filter(
        store=store, status=ContentPage.Status.PUBLISHED,
    ).order_by("slug")[:SITEMAP_LIMIT]
    for page in pages:
        loc = link(reverse("content:page-detail", args=[page.slug]))
        entries.append({"loc": loc, "lastmod": getattr(page, "updated_at", None), "priority": "0.4"})

    return entries


def sitemap_xml(request):
    """sitemap.xmlِ محدود به این Store."""
    store = resolve_store_for_storefront(request)
    # a test host (localhost…) or a Store that is not public yet has NO sitemap: nothing may be offered to a search engine
    if not seo_policy.indexability(request, store).indexable:
        raise Http404("sitemap not available")
    entries = _sitemap_entries(request, store, origin=seo_policy.canonical_origin(request, store))
    return render(
        request, "seo/sitemap.xml", {"entries": entries}, content_type="application/xml",
    )


def robots_txt(request):
    """robots.txt — مسیرهایِ خصوصی (سبد/تسویه/حساب) را از ایندکس کنار می‌گذارد، خزنده‌هایِ «آموزشِ مدل» را (طبقِ سیاستِ پلتفرم)
    می‌بندد، به sitemapِ دامنه‌یِ canonical اشاره می‌کند، و روی آدرسِ آزمایشی/فروشگاهِ منتشرنشده همه‌چیز را می‌بندد."""
    try:
        store = resolve_store_for_storefront(request)
    except Exception:                                         # noqa: BLE001 - an unknown host is simply not indexable
        store = None
    state = seo_policy.indexability(request, store)
    origin = seo_policy.canonical_origin(request, store) if state.indexable else ""
    return HttpResponse("\n".join(seo_policy.robots_lines(origin=origin, indexable=state.indexable)), content_type="text/plain")
