"""Non-destructive QA seed/revert helper for PDTX browser QA (dedicated QA tenant).

Usage (``manage.py shell < file`` does NOT forward argv, so the mode is chosen
via the ``PDTX_QA_MODE`` environment variable):

  PDTX_QA_MODE=seed   python manage.py shell < tools/storefront_builder_qa/_pdtx_seed.py
  PDTX_QA_MODE=revert python manage.py shell < tools/storefront_builder_qa/_pdtx_seed.py

``seed`` adds (or refreshes) exactly ONE helper-owned, EDITED, PUBLISHED
``product_detail`` ``trust_features`` section on the QA tenant so the browser QA
can assert PDTX render health (published trust marker visible + hard-coded strip
suppressed). ``revert`` removes ONLY that helper-owned section and re-publishes,
restoring the exact prior state (the default hard-coded PDP fallback).

Safety (fail-closed): the helper NEVER deletes arbitrary merchant/QA config. If
the PDP already carries a ``trust_features`` section that is NOT this helper's
own QA marker, both ``seed`` and ``revert`` STOP with a clear error and change
nothing — a human must resolve it. This makes the helper repeatable and safe to
run on the shared QA tenant.

No model, no migration, no persistent QA flag is introduced — "helper-owned" is
recognised purely by the section's own settings content (a single item whose
title is the QA MARKER below).
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
QA_ITEMS = [{"icon": "🏅", "title": MARKER, "subtitle": "کیوای"}]


class _PdtxSeedAborted(RuntimeError):
    """Raised (and reported) when a pre-existing non-QA section blocks us."""


def _is_helper_owned(section) -> bool:
    """True IFF this section is exactly the helper's own QA state — a single
    item whose title is the QA MARKER. Any other content means it belongs to a
    merchant / another QA run and must never be touched."""
    items = (section.settings or {}).get("items") or []
    return len(items) == 1 and str(items[0].get("title", "")) == MARKER


mode = os.environ.get("PDTX_QA_MODE") or (sys.argv[-1] if len(sys.argv) > 1 else "seed")
store = Store.objects.get(slug=SLUG)
draft = svc.get_or_create_draft(store)
pdp = draft.get_page(StorefrontPage.PageType.PRODUCT_DETAIL)
existing = list(pdp.sections.filter(section_key="trust_features"))
foreign = [s for s in existing if not _is_helper_owned(s)]

try:
    if foreign:
        raise _PdtxSeedAborted(
            "ABORTED: the QA tenant PDP already has a non-QA trust_features "
            "section (not this helper's marker). Refusing to modify it. "
            "Resolve manually before running PDTX QA."
        )

    if mode == "seed":
        section = existing[0] if existing else section_structure_service.add_section(
            draft=draft, section_key="trust_features",
            page_type=StorefrontPage.PageType.PRODUCT_DETAIL,
        )
        section.settings = section_registry.validate_trust_features_settings({"items": QA_ITEMS})
        section.save(update_fields=["settings"])
        svc.publish(store)
        print("SEEDED", MARKER)
    elif mode == "revert":
        # Only ever removes the helper-owned QA section(s) (foreign already
        # excluded above). Restores the exact prior default PDP.
        for section in existing:
            section.delete()
        svc.publish(store)
        print("REVERTED")
    else:
        raise _PdtxSeedAborted(f"ABORTED: unknown PDTX_QA_MODE={mode!r} (use seed|revert)")
except _PdtxSeedAborted as exc:
    print(str(exc))
    sys.exit(3)
