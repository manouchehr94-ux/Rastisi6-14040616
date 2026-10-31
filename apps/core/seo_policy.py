"""One place that decides WHERE and HOW a storefront may be indexed — robots.txt, the sitemap, ``<meta robots>``, canonical URLs and the
setup checklist all read it, so they can never disagree.

Rules (no guesswork, no external calls):

* A page is *indexable* only when the Store is publicly visible (publication authority) AND the host the crawler used is a real public
  host. ``localhost``, ``*.localhost``, ``*.local``, ``*.test``, ``*.invalid``, ``*.example`` and raw IPs are test hosts and are never
  offered to search engines — a QA or preview address must not become a public, duplicate copy of the shop.
* The canonical origin of a Store is its preferred public storefront URL (``resolve_storefront_url_for_store``: verified custom domain, then
  the claimed platform subdomain, then the trial subdomain). Every host that serves the same shop points to it, which stops duplicate
  content between the free address and a custom domain.
* AI crawlers are two different things and are controlled separately: SEARCH crawlers (they answer a user's question and cite the page)
  stay allowed; TRAINING crawlers are blocked by default (platform setting ``RASTISI_AI_TRAINING_CRAWLERS`` = ``allow`` / ``disallow``).
  Allowing a page to be crawled never publishes anything private: the private paths are disallowed for every group.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from urllib.parse import urlsplit

from django.conf import settings

#: hostnames that can never be a public storefront address
NON_PUBLIC_SUFFIXES = (".localhost", ".local", ".test", ".invalid", ".example", ".internal")

#: paths that no crawler of any kind should fetch (customer, money and admin areas)
PRIVATE_DISALLOW = ("/cart/", "/checkout/", "/account/", "/admin/", "/admin-portal/", "/admin-panel/")

#: crawlers whose purpose is TRAINING models (not answering a user's search). Blocked unless the platform allows them.
AI_TRAINING_CRAWLERS = ("GPTBot", "Google-Extended", "CCBot", "ClaudeBot", "anthropic-ai", "Applebot-Extended", "Bytespider")
#: crawlers that power AI SEARCH / answer engines: they are NOT blocked (visibility is the goal); listed for the readiness card
AI_SEARCH_CRAWLERS = ("OAI-SearchBot", "PerplexityBot", "Googlebot", "Bingbot")

REASONS_FA = {
    "indexable": "فروشگاه عمومی است و خزنده‌های جست‌وجو اجازهٔ دسترسی دارند.",
    "test_host": "این آدرس مخصوص آزمایش است (مثل localhost)؛ موتورهای جست‌وجو آن را نمی‌بینند.",
    "store_not_public": "فروشگاه هنوز منتشر نشده یا دسترسی عمومی آن محدود است؛ تا انتشار، موتورهای جست‌وجو آن را نمی‌بینند.",
}


def hostname_of(host: str) -> str:
    host = (host or "").strip().lower()
    if host.startswith("["):                                       # [::1]:8000
        return host[1:].split("]", 1)[0]
    return host.rsplit(":", 1)[0] if host.count(":") == 1 else host


def is_non_public_host(host: str) -> bool:
    name = hostname_of(host)
    if not name:
        return True
    if name == "localhost":
        return True
    try:
        ipaddress.ip_address(name)
        return True
    except ValueError:
        pass
    return name.endswith(NON_PUBLIC_SUFFIXES)


@dataclass(frozen=True)
class Indexability:
    indexable: bool
    code: str

    @property
    def reason_fa(self) -> str:
        return REASONS_FA[self.code]


def indexability(request, store) -> Indexability:
    """Is THIS request on THIS Store something search engines may index?"""
    if store is None:
        return Indexability(False, "store_not_public")
    if is_non_public_host(request.get_host()):
        return Indexability(False, "test_host")
    from apps.stores.services.publication_service import is_publicly_visible

    if not is_publicly_visible(store):
        return Indexability(False, "store_not_public")
    return Indexability(True, "indexable")


def canonical_origin(request, store) -> str:
    """``scheme://host`` every canonical / sitemap / structured-data URL of this Store is built on."""
    fallback = f"{request.scheme}://{request.get_host()}"
    if store is None:
        return fallback
    from apps.stores.resolution import resolve_storefront_url_for_store

    try:
        url = resolve_storefront_url_for_store(store, request)
    except Exception:                                               # noqa: BLE001 - SEO must never break a page render
        url = None
    if not url:
        return fallback
    parts = urlsplit(url)
    if not parts.scheme or not parts.netloc:
        return fallback
    return f"{parts.scheme}://{parts.netloc}"


def ai_training_blocked() -> bool:
    return str(getattr(settings, "RASTISI_AI_TRAINING_CRAWLERS", "disallow")).strip().lower() != "allow"


def robots_lines(*, origin: str, indexable: bool) -> list[str]:
    """The body of robots.txt. Not indexable → everything is disallowed and no sitemap is advertised."""
    if not indexable:
        return ["User-agent: *", "Disallow: /", ""]
    lines = ["User-agent: *", *(f"Disallow: {path}" for path in PRIVATE_DISALLOW), ""]
    if ai_training_blocked():
        for bot in AI_TRAINING_CRAWLERS:
            lines += [f"User-agent: {bot}", "Disallow: /", ""]
    lines += [f"Sitemap: {origin}/sitemap.xml", ""]
    return lines
