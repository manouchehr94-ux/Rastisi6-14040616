from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST

from apps.core.services.rate_limit import RateLimitExceeded, enforce_rate_limit
from apps.stores.resolution import resolve_store_for_storefront

from .models import ContentPage
from .services import NewsletterSubscribeError, subscribe_to_newsletter


def page_detail(request, slug):
    """نمایش صفحه‌ی محتوایی منتشرشده — مقیّد به فروشگاه جاری.

    P5-W4A — converges onto the canonical universal storefront shell (see
    storefront_context_service.build_universal_storefront_context's
    shell_only contract). Local import: matches the existing
    catalog/cart/home() call-site convention that avoids a module-level
    dependency on apps.storefront_builder."""
    from apps.storefront_builder.services.storefront_context_service import (
        build_universal_storefront_context,
    )

    store = resolve_store_for_storefront(request)
    page = get_object_or_404(
        ContentPage, slug=slug, status=ContentPage.Status.PUBLISHED, store=store,
    )
    context = {"page": page}
    context.update(
        build_universal_storefront_context(
            request, store, "content_page", page_context=context, shell_only=True,
        )
    )
    return render(request, "content/page_detail.html", context)


@require_POST
def newsletter_subscribe(request):
    """ثبتِ ایمیل از بلوکِ «خبرنامه»یِ سازنده بصری — عمومی (بدونِ نیازِ
    لاگین)، پس با ``enforce_rate_limit`` (همان زیرساختِ فرم‌هایِ عمومیِ
    سایت — OTP/فرمِ تماس) در برابرِ اسپم محافظت می‌شود. htmx-اول: پاسخ
    همیشه همان partial را دوباره رندر می‌کند (فرم یا وضعیتِ موفق)، نه
    redirect — دقیقاً همان الگویِ ``product_review_create``."""
    store = resolve_store_for_storefront(request)
    ip_address = request.META.get("REMOTE_ADDR", "unknown")

    try:
        enforce_rate_limit("newsletter_subscribe_ip", ip_address, max_attempts=8, window_seconds=300)
    except RateLimitExceeded as exc:
        return render(request, "content/partials/newsletter_form.html", {"error": str(exc)})

    try:
        subscribe_to_newsletter(store, request.POST.get("email", ""))
    except NewsletterSubscribeError as exc:
        return render(request, "content/partials/newsletter_form.html", {"error": str(exc)})

    return render(request, "content/partials/newsletter_form.html", {"subscribed": True})
