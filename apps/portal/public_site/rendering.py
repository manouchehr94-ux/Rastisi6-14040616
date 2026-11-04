"""``render`` drop-in for ``apps.portal.views``.

For templates under ``portal/public/`` it serves the matching ``portal/public_v2/``
template when the new design is active (and that template exists). Every other
template — and every page when the owner (or the ``RASTISI_PUBLIC_SITE_DESIGN``
emergency setting) selects the previous design — goes through Django's ``render``
unchanged. So the previous design stays fully intact as the rollback path.
"""

from django.shortcuts import render as django_render
from django.template import TemplateDoesNotExist
from django.template.loader import select_template

from . import services

LEGACY_PREFIX = "portal/public/"
V2_PREFIX = "portal/public_v2/"


def template_for(request, template_name):
    if isinstance(template_name, str) and template_name.startswith(LEGACY_PREFIX):
        if services.active_design(request) == "v2":
            candidate = V2_PREFIX + template_name[len(LEGACY_PREFIX):]
            try:
                select_template([candidate])
                return candidate
            except TemplateDoesNotExist:
                pass
    return template_name


def render(request, template_name, context=None, *args, **kwargs):
    return django_render(request, template_for(request, template_name), context, *args, **kwargs)
