"""Template API of the editable public website. Used only by ``portal/public_v2``.

    {% ps 'home.hero.title' %}                 text (auto-escaped, tokens applied)
    {% ps 'plans.trial' days=3 %}              extra {days} token
    {% ps_on 'x.hide' as hidden %}             bool switch
    {% ps_items 'faq' as rows %}               list rows (hidden/empty rows skipped)
    {% ps_photo 'bag' as img %}                image {url, alt}  (owner override or bundled)
    {% ps_theme %}                             <style>/<link> with the owner's colours & fonts
    {% ps_demo_data %}                         JSON for the landing demo
"""

from types import SimpleNamespace

from django import template
from django.utils.html import format_html, json_script
from django.utils.safestring import mark_safe

from apps.portal.public_site import services

register = template.Library()


def _request(context):
    """The request, or — when a template is rendered without one — a per-render holder so the
    overrides are still loaded only once."""
    request = context.get("request")
    if request is not None:
        return request
    holder = context.render_context.get("ps_holder")
    if holder is None:
        holder = context.render_context["ps_holder"] = SimpleNamespace()
    return holder


@register.simple_tag(takes_context=True)
def ps(context, key, **extra):
    return services.value(key, _request(context), **extra)


@register.simple_tag(takes_context=True)
def ps_on(context, key):
    return services.truthy(key, _request(context))


@register.simple_tag(takes_context=True)
def ps_items(context, prefix):
    return services.list_items(prefix, _request(context))


@register.simple_tag(takes_context=True)
def ps_photo(context, slot):
    return services.photo(slot, _request(context))


@register.simple_tag(takes_context=True)
def ps_theme(context):
    request = _request(context)
    out = []
    sheet = services.font_stylesheet_url(request)
    if sheet:
        out.append(format_html('<link rel="stylesheet" href="{}">', sheet))
    css = services.theme_css(request)
    if css:
        # Built only from validated hex colours, preset font stacks and a sanitised font name.
        out.append(mark_safe(f'<style id="ps-theme">{css}</style>'))
    return mark_safe("".join(str(x) for x in out))


@register.simple_tag
def ps_unique(rows, name):
    """Distinct non-empty values of one field, in first-seen order (category filters)."""
    seen = []
    for row in rows or ():
        value = row.get(name)
        if value and value not in seen:
            seen.append(value)
    return seen


@register.simple_tag(takes_context=True)
def ps_faq_groups(context):
    """FAQ rows grouped by category, categories in first-seen order."""
    groups = []
    for row in services.list_items("faq", _request(context)):
        for group in groups:
            if group["cat"] == row["cat"]:
                group["items"].append(row)
                break
        else:
            groups.append({"cat": row["cat"], "items": [row]})
    return groups


@register.simple_tag(takes_context=True)
def ps_faq_jsonld(context):
    """schema.org FAQPage built from the same (editable) rows the page shows."""
    import json

    rows = services.list_items("faq", _request(context))
    data = {
        "@context": "https://schema.org", "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": r["q"], "acceptedAnswer": {"@type": "Answer", "text": r["a"]}}
            for r in rows
        ],
    }
    text = json.dumps(data, ensure_ascii=False)
    return mark_safe(text.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026"))


@register.simple_tag
def ps_year():
    """Current Jalali year in Persian digits (copyright line)."""
    from apps.core.utils import to_fa_digits

    try:
        import jdatetime

        return to_fa_digits(jdatetime.date.today().year)
    except Exception:
        from django.utils import timezone

        return to_fa_digits(timezone.now().year)


@register.simple_tag(takes_context=True)
def ps_demo_data(context):
    return json_script(services.demo_payload(_request(context)), "ps-demo-data")
