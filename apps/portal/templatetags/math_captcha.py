"""Template API of the math CAPTCHA (see ``apps.portal.services.captcha_service``).

    {% math_captcha 'login_password' as captcha %}      issue a fresh question for this form (once per render)
    {% include "portal/public/_captcha.html" with captcha=captcha %}

Without a request in the context (a template rendered outside a view) nothing is issued and the form shows the "unavailable" state,
so a question can never be created for a visitor who has no session to bind it to.
"""

from django import template

from apps.portal.services import captcha_service

register = template.Library()


@register.simple_tag(takes_context=True)
def math_captcha(context, action):
    request = context.get("request")
    if request is None or not hasattr(request, "session"):
        return {"enabled": captcha_service.is_enabled(), "unavailable": True}
    return captcha_service.issue(request, action)
