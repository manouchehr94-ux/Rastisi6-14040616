from django import template
from django.utils.html import json_script

register = template.Library()


@register.filter
def track_events_script(events, element_id):
    """Print the validated tracking events of this page as ``<script type="application/json">`` (empty when there are none)."""
    return json_script(list(events), element_id) if events else ""


@register.filter
def consent_json_script(config, element_id):
    """Print the consent config as ``<script type="application/json">`` (``<``, ``>``, ``&`` escaped by Django). ``config`` arrives as a lazy
    proxy from the context processor, which the JSON encoder cannot serialise directly — unwrap it into a plain dict first."""
    return json_script(dict(config), element_id) if config else ""
