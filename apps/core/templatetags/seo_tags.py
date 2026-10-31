"""Structured data (JSON-LD) built from the Store's REAL data — one safe implementation instead of hand-written JSON in templates.

* The JSON is produced by ``json.dumps`` (never string-pasted) and ``<``, ``>``, ``&`` are escaped, so a product name can never close the
  ``<script>`` tag.
* Everything comes from the database: name, SKU, brand, price, availability, images, category. No rating, review, shipping or return
  policy is ever invented — a field without data is omitted, not guessed.
* URLs use the Store's canonical origin (``SEO_ORIGIN``), identical to the canonical link and the sitemap."""

import json

from django import template
from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe

register = template.Library()

_ESCAPES = {ord("<"): "\\u003c", ord(">"): "\\u003e", ord("&"): "\\u0026", 0x2028: "\\u2028", 0x2029: "\\u2029"}


def dump(data: dict) -> str:
    """Compact, script-safe JSON for an ``application/ld+json`` block."""
    return mark_safe(json.dumps(data, ensure_ascii=False, separators=(",", ":")).translate(_ESCAPES))


def _origin(context) -> str:
    request = context.get("request")
    origin = str(context.get("SEO_ORIGIN") or "")           # lazy value from the context processor → plain str
    return origin or (f"{request.scheme}://{request.get_host()}" if request else "")


def _absolute(origin: str, url: str) -> str:
    return url if str(url).startswith(("http://", "https://")) else f"{origin}{url}"


@register.simple_tag(takes_context=True)
def jsonld_store(context):
    """Organization + WebSite of the Store (home page)."""
    origin = _origin(context)
    name = context.get("SHOP_NAME") or ""
    organization = {"@type": "Organization", "@id": f"{origin}/#organization", "name": name, "url": f"{origin}/"}
    logo = context.get("SHOP_LOGO")
    if logo:
        try:
            organization["logo"] = _absolute(origin, logo.url)
        except ValueError:                                         # no file behind the field
            pass
    website = {"@type": "WebSite", "@id": f"{origin}/#website", "url": f"{origin}/", "name": name,
               "publisher": {"@id": f"{origin}/#organization"}, "inLanguage": "fa"}
    list_url = reverse("catalog:product-list")
    website["potentialAction"] = {"@type": "SearchAction", "target": f"{origin}{list_url}?q={{search_term_string}}",
                                  "query-input": "required name=search_term_string"}
    return dump({"@context": "https://schema.org", "@graph": [organization, website]})



def _offers(product, url: str):
    """schema.org Offer / AggregateOffer from the SAME pricing authority the cart and checkout use (``resolve_effective_price``), in ISO 4217
    Rials (stored Toman × 10 — see ``apps.core.currency``). A variable product whose active variants have different prices is an
    AggregateOffer (low/high), never a single invented price. ``None`` for a price-inquiry product."""
    from apps.catalog.services.pricing_service import resolve_effective_price
    from apps.core.currency import ISO_CURRENCY, toman_to_rial

    if getattr(product, "is_price_inquiry", False):
        return None
    variants = []
    if getattr(product, "is_variable", False):
        variants = list(product.variants.filter(is_active=True, is_obsolete=False))
    if variants:
        prices = sorted({toman_to_rial(resolve_effective_price(product, v)) for v in variants})
        in_stock = any(v.stock > 0 for v in variants)
    else:
        prices = [toman_to_rial(resolve_effective_price(product))]
        in_stock = product.stock > 0
    availability = "https://schema.org/" + ("InStock" if in_stock else "OutOfStock")
    if len(prices) == 1:
        return {"@type": "Offer", "priceCurrency": ISO_CURRENCY, "price": str(prices[0]), "availability": availability, "url": url}
    return {"@type": "AggregateOffer", "priceCurrency": ISO_CURRENCY, "lowPrice": str(prices[0]), "highPrice": str(prices[-1]),
            "offerCount": len(variants), "availability": availability, "url": url}


@register.simple_tag
def og_price_meta(product):
    """``product:price:*`` Open Graph tags in ISO currency (lowest price for a variable product); nothing for a price-inquiry product."""
    offers = _offers(product, "")
    if not offers:
        return ""
    amount = offers.get("price") or offers.get("lowPrice")
    return format_html('<meta property="product:price:amount" content="{}">\n<meta property="product:price:currency" content="{}">',
                       amount, offers["priceCurrency"])

@register.simple_tag(takes_context=True)
def jsonld_product(context, product):
    """Product (+ Offer) and its BreadcrumbList. Only facts the Store really has."""
    origin = _origin(context)
    url = f"{origin}{reverse('catalog:product-detail', args=[product.slug])}"
    node = {"@type": "Product", "@id": f"{url}#product", "name": product.name, "sku": product.sku, "url": url}
    description = (getattr(product, "seo_description", "") or "").strip()
    if description:
        node["description"] = description
    if getattr(product, "brand", None):
        node["brand"] = {"@type": "Brand", "name": product.brand.name}
    images = []
    for slide in context.get("gallery_slides") or []:
        link = slide.get("url") if isinstance(slide, dict) else getattr(slide, "url", "")
        if link and _absolute(origin, link) not in images:
            images.append(_absolute(origin, link))
    if images:
        node["image"] = images[0] if len(images) == 1 else images[:8]
    offers = _offers(product, url)
    if offers:
        node["offers"] = offers
    crumbs = [{"@type": "ListItem", "position": 1, "name": "خانه", "item": f"{origin}/"}]
    if getattr(product, "category", None):
        crumbs.append({"@type": "ListItem", "position": 2, "name": product.category.name,
                       "item": f"{origin}{reverse('catalog:product-list')}?category={product.category.slug}"})
    crumbs.append({"@type": "ListItem", "position": len(crumbs) + 1, "name": product.name})
    return dump({"@context": "https://schema.org", "@graph": [node, {"@type": "BreadcrumbList", "itemListElement": crumbs}]})
