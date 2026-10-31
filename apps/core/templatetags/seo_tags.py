"""Structured data (JSON-LD) built from the Store's REAL data — one safe implementation instead of hand-written JSON in templates.

* The JSON is produced by ``json.dumps`` (never string-pasted) and ``<``, ``>``, ``&`` are escaped, so a product name can never close the
  ``<script>`` tag.
* Everything comes from the database: name, SKU, brand, price, availability, images, category. No rating, review, shipping or return
  policy is ever invented — a field without data is omitted, not guessed.
* URLs use the Store's canonical origin (``SEO_ORIGIN``), identical to the canonical link and the sitemap."""

import json

from django import template
from django.urls import reverse
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
    if not getattr(product, "is_price_inquiry", False):
        node["offers"] = {
            "@type": "Offer", "priceCurrency": "IRT", "price": str(product.final_price),
            "availability": "https://schema.org/" + ("InStock" if product.stock > 0 else "OutOfStock"), "url": url,
        }
    crumbs = [{"@type": "ListItem", "position": 1, "name": "خانه", "item": f"{origin}/"}]
    if getattr(product, "category", None):
        crumbs.append({"@type": "ListItem", "position": 2, "name": product.category.name,
                       "item": f"{origin}{reverse('catalog:product-list')}?category={product.category.slug}"})
    crumbs.append({"@type": "ListItem", "position": len(crumbs) + 1, "name": product.name})
    return dump({"@context": "https://schema.org", "@graph": [node, {"@type": "BreadcrumbList", "itemListElement": crumbs}]})
