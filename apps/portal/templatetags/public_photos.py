"""Dynamic public-site marketing photos with a version-controlled static fallback.

Used only from portal/public templates; no storefront or tenant theme touches
this tag. Overrides are owned by superusers through Platform Admin.
"""

from urllib.parse import urlsplit

from django import template
from django.templatetags.static import static

from apps.portal.models import PublicSitePhoto


register = template.Library()
_VALID_SLOTS = frozenset(slot for slot, _ in PublicSitePhoto.SLOT_CHOICES)


@register.simple_tag(takes_context=True)
def public_photo(context, slot):
    if slot not in _VALID_SLOTS:
        raise ValueError("Unknown public-site photo slot")

    # One query per rendered page even when a photo appears multiple times.
    photos = context.render_context.get("public_site_photo_overrides")
    if photos is None:
        photos = {photo.slot: photo for photo in PublicSitePhoto.objects.all()}
        context.render_context["public_site_photo_overrides"] = photos

    current = photos.get(slot)
    if current and current.image:
        url = current.image.url
        if not urlsplit(url).scheme and not url.startswith("/"):
            url = "/" + url
        return {"url": url, "alt": current.alt_text}

    return {
        "url": static(f"portal/images/public/{slot}.webp"),
        "alt": "",
    }
