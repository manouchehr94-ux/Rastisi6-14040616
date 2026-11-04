"""Vision Studio only: the read-only «what would this header / footer model look like» preview.

It renders ONLY the asked region (the other region and the page body are not rendered at all), with the Store's own Draft data and the very same
shell templates as the Studio Preview; the renderer comes from ``global_region_registry`` for the asked variant key instead of the one the Draft stores. Nothing is written, no Draft
is created, and the variant is never taken from the request as a path - only as a registry key that must resolve (anything else is a 400).
The Studio gallery shows it in a large dialog (live, with the Store's own logo / menu / colours) and the build-time command
``capture_global_region_previews`` photographs it with fixed sample data for the gallery thumbnails."""

from django.http import Http404, HttpResponseBadRequest
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_GET

from apps.dashboard.decorators import permission_required, staff_required
from apps.stores.authorization import STOREFRONT_LAYOUT_MANAGE

from . import global_region_registry
from .services import layout_service
from .services.render_service import resolved_store_appearance_for_request
from .views import _resolve_page_type, _resolve_store

PREVIEW_TEMPLATE = "dashboard/vision/region_preview.html"

#: the two regions that have a visual gallery (the mobile bottom bar keeps its own select)
GALLERY_REGIONS = {
    "header": (global_region_registry.GLOBAL_HEADER_REGION, "header_variant"),
    "footer": (global_region_registry.GLOBAL_FOOTER_REGION, "footer_variant"),
}


class _VariantPreviewVersion:
    """A view of the Draft whose header / footer config carries the candidate variant. Template code only calls ``effective_*_config``,
    ``effective_appearance_config`` and reads plain attributes, so the rest is delegated to the (unchanged, unsaved) Draft."""

    def __init__(self, draft, header_config, footer_config):
        self._draft = draft
        self._header_config = header_config
        self._footer_config = footer_config

    def effective_header_config(self):
        return dict(self._header_config)

    def effective_footer_config(self):
        return dict(self._footer_config)

    def __getattr__(self, name):
        return getattr(self._draft, name)


@never_cache
@require_GET
@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
@xframe_options_sameorigin
def region_variant_preview(request):
    region_key = request.GET.get("region", "")
    variant_key = request.GET.get("variant", "")
    if region_key not in GALLERY_REGIONS:
        return HttpResponseBadRequest("region must be header or footer")
    region, selector_key = GALLERY_REGIONS[region_key]
    variant = global_region_registry.get_global_variant(region, variant_key)
    if variant is None:
        return HttpResponseBadRequest("unknown variant")

    store = _resolve_store(request)
    draft = layout_service.get_existing_draft(store)
    if draft is None:
        raise Http404("no Draft yet")
    page_type = _resolve_page_type(request.GET.get("page"))
    header_config = draft.effective_header_config()
    footer_config = draft.effective_footer_config()
    # exactly what picking this model would store: the variant key changes, everything else (toggles, geometry) stays
    if region_key == "header":
        header_config = {**header_config, selector_key: variant.key}
    else:
        footer_config = {**footer_config, selector_key: variant.key}
    version = _VariantPreviewVersion(draft, header_config, footer_config)
    store_appearance = resolved_store_appearance_for_request(request, draft)
    request.storefront_appearance_version = draft
    request.storefront_appearance_page = draft.get_page(page_type)

    return render(request, PREVIEW_TEMPLATE, {
        "store": store, "version": version, "page_type": page_type, "store_appearance": store_appearance,
        # ONLY the asked region is rendered: the other one (and the page body between them) is not even resolved
        "region": region_key, "variant": variant, "variant_template": variant.renderer, "is_preview": True,
    })
