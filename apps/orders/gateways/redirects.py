"""Browser hand-off to a provider payment page.

Most providers are reached with a plain 302. Providers whose contract demands ``Referer: <merchant domain>`` on that
navigation (``adapter.redirect_requires_referer`` — Pasargad/Dorsa) cannot be: Django's default
``Referrer-Policy: same-origin`` drops the Referer on a cross-origin redirect. For those we return a tiny interstitial
document that declares ``<meta name="referrer" content="origin">`` and navigates with ``<meta http-equiv="refresh">``
(no inline script, so it also works under a strict CSP); the browser then sends ``Referer: https://<our origin>/``.

Callers must already have validated ``url`` (``is_safe_gateway_redirect``)."""

from django.http import HttpResponse, HttpResponseRedirect
from django.utils.html import escape


def gateway_redirect_response(url: str, *, adapter=None, post_fields=None):
    """``post_fields``: درگاه‌هایی که صفحه‌ی پرداخت را با **فرمِ POST** می‌خواهند (ملت: ``RefId``؛ سپ: ``Token``). فرمِ HTML
    (مقادیر escape‌شده، بدونِ ذخیره) با ارسالِ خودکار؛ برای کاربرِ بدونِ JS دکمه‌ی دستی هست."""
    if post_fields:
        inputs = "".join(
            f'<input type="hidden" name="{escape(str(k))}" value="{escape(str(v))}">' for k, v in dict(post_fields).items()
        )
        safe_action = escape(url)
        html = (
            '<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1"><meta name="robots" content="noindex,nofollow">'
            '<meta name="referrer" content="origin"><title>انتقال به درگاه پرداخت</title></head>'
            '<body style="font-family:Tahoma,sans-serif;text-align:center;padding:48px 16px" onload="document.forms[0].submit()">'
            f'<p>در حال انتقال به درگاه پرداخت…</p><form method="post" action="{safe_action}">{inputs}'
            '<noscript><button type="submit">ادامه به درگاه پرداخت</button></noscript></form></body></html>'
        )
        response = HttpResponse(html)
        response["Referrer-Policy"] = "origin"
        response["Cache-Control"] = "no-store"
        return response
    if not (adapter is not None and getattr(adapter, "redirect_requires_referer", False)):
        return HttpResponseRedirect(url)
    safe = escape(url)
    html = (
        '<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<meta name="robots" content="noindex,nofollow"><meta name="referrer" content="origin">'
        f'<meta http-equiv="refresh" content="0;url={safe}"><title>انتقال به درگاه پرداخت</title></head>'
        f'<body style="font-family:Tahoma,sans-serif;text-align:center;padding:48px 16px">'
        f'<p>در حال انتقال به درگاه پرداخت…</p><p><a href="{safe}" referrerpolicy="origin">اگر منتقل نشدید اینجا را بزنید</a></p>'
        "</body></html>"
    )
    response = HttpResponse(html)
    response["Referrer-Policy"] = "origin"
    response["Cache-Control"] = "no-store"
    return response
