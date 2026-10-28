from django import template

from .. import vision_ux

register = template.Library()


@register.simple_tag
def vision_gallery_data():
    """Header / footer model galleries (registry data + pre-rendered thumbnails) for the Vision Studio page."""
    return vision_ux.gallery_data()


@register.simple_tag
def vision_ux_data():
    """Plain-language setting wording + switch polarity rules for the Vision Studio page."""
    return vision_ux.ux_data()
