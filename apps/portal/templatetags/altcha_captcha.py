"""Render a local ALTCHA checkbox, bound to the public form's session/action."""

from django import template
from apps.portal.services import captcha_service

register = template.Library()


@register.simple_tag(takes_context=True)
def altcha_captcha(context, action):
    request = context.get("request")
    if request is None or not hasattr(request, "session"):
        return {"enabled": captcha_service.is_enabled(), "unavailable": True}
    return captcha_service.widget_config(request, action)


@register.simple_tag(takes_context=True)
def captcha_assets_enabled(context):
    request = context.get("request")
    return (
        captcha_service.is_enabled()
        and request is not None
        and getattr(request, "path", "")
        in {
            "/login/",
            "/login/password/",
            "/register/",
            "/reset-password/",
            "/contact/",
        }
    )
