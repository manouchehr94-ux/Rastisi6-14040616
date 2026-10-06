import json

from django import template
from django.conf import settings
from django.utils.safestring import mark_safe

from ..services import enablement

register = template.Library()


@register.simple_tag(takes_context=True)
def rastichat_widget(context):
    """The storefront chat launcher. Renders NOTHING unless the integration is globally on, the store is active and the
    platform enabled chat for THIS store — so adding this tag to the base template changes nothing by default.

    The only values emitted are the store's public project key (public by design) and URLs from settings; identity comes
    exclusively from `bootstrap`, which calls this site's own `/chat/identity/` (server-side session)."""
    request = context.get("request")
    store = getattr(request, "store", None)
    if not enablement.chat_enabled_for_store(store):
        return ""
    from .. import conf
    cfg = {
        "projectKey": enablement.project_public_key(store), "apiBase": conf.api_base(), "wsBase": conf.ws_base(),
        "context": {"page": request.path[:200]},
    }
    # JSON for a <script>: escape the characters that could close the tag
    blob = json.dumps(cfg, ensure_ascii=True).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    return mark_safe(
        f'<script src="{settings.RASTICHAT_WIDGET_URL}" defer></script>\n'
        f'<script>window.addEventListener("load", function () {{ var c = {blob};'
        f' c.bootstrap = function () {{ return fetch("/chat/identity/", {{ credentials: "same-origin" }})'
        f'.then(function (r) {{ return r.ok ? r.text() : null; }}).catch(function () {{ return null; }}); }};'
        f' if (window.RastiChat) window.RastiChat.init(c); }});</script>'
    )
