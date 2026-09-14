"""One-shot QA seed/revert helper for PDTX browser QA (dev tenant).

Usage:
  python manage.py shell < tools/storefront_builder_qa/_pdtx_seed.py seed
  python manage.py shell < tools/storefront_builder_qa/_pdtx_seed.py revert

Adds (seed) or removes (revert) an EDITED, PUBLISHED product_detail
``trust_features`` section on the QA tenant so the deepened browser QA can
assert PDTX render health (published trust visible + hard-coded strip
suppressed). Reverting restores the original default PDP (hard-coded fallback).
"""
import os
import sys

from apps.stores.models import Store
from apps.storefront_builder.models import StorefrontPage
from apps.storefront_builder.services import layout_service as svc
from apps.storefront_builder.services import section_structure_service
from apps.storefront_builder import section_registry

MARKER = "ضمانت‌کیوایِ‌قابل‌ویرایش"
SLUG = "rastisi-fashion-test"

# `manage.py shell < file` does not forward argv; select mode via env var.
mode = os.environ.get("PDTX_QA_MODE") or (sys.argv[-1] if len(sys.argv) > 1 else "seed")
store = Store.objects.get(slug=SLUG)
draft = svc.get_or_create_draft(store)
pdp = draft.get_page(StorefrontPage.PageType.PRODUCT_DETAIL)

if mode == "seed":
    pdp.sections.filter(section_key="trust_features").delete()
    section = section_structure_service.add_section(
        draft=draft, section_key="trust_features",
        page_type=StorefrontPage.PageType.PRODUCT_DETAIL,
    )
    section.settings = section_registry.validate_trust_features_settings(
        {"items": [{"icon": "🏅", "title": MARKER, "subtitle": "کیوای"}]}
    )
    section.save(update_fields=["settings"])
    svc.publish(store)
    print("SEEDED", MARKER)
elif mode == "revert":
    pdp.sections.filter(section_key="trust_features").delete()
    svc.publish(store)
    print("REVERTED")
