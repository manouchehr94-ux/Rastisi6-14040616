"""Golden Reference Storefront (G1) — composition service.

The Golden Reference Storefront is the customized ``rasti-mode-demo`` store: a
visually complete premium multi-brand fashion/lifestyle storefront that a
prospective merchant can visit to understand what a finished RastiSi store
looks like.

Design authority:
``docs/superpowers/specs/2026-09-04-golden-reference-storefront-design.md``
Executable plan:
``docs/superpowers/plans/2026-09-04-golden-reference-storefront-g1-plan.md``

Architecture model (this is the load-bearing correctness contract):

  A Ready Template's identity + version must always describe its **actual
  registered authored DNA**. So the Golden setup does NOT hand a modified
  preset object to ``apply_preset`` while keeping the official key/version —
  that would make ``template_baseline_snapshot`` (the pure authored template
  truth the future Phase-1 reset relies on) lie about what the template
  authored.

  Instead the Golden setup mirrors exactly what a real merchant does:

    1. Seed the resettable ``rasti-mode-demo`` (real catalog/content).
    2. Obtain the REAL registered ``fashion_promo_catalog`` recipe.
    3. Apply that real preset normally (``preset_service.apply_preset``) so the
       Draft carries honest ``template_provenance`` AND a truthful
       ``template_baseline_snapshot`` = the authored ``fashion_promo_catalog``
       baseline.
    4. Customize the resulting Draft the way a merchant would, through existing
       production contracts — palette selection, Store-Appearance manifest
       (header/footer/bottom-nav), header config, and Home section
       composition. These writes NEVER touch ``template_baseline_snapshot``, so
       the live Draft becomes ``authored baseline + Golden merchant
       divergences`` — precisely the model future Phase-1 semantics expect.
    5. Publish.

The live Golden Draft may (and does) differ substantially from the
``fashion_promo_catalog`` authored baseline. That is intended.

No new Ready Template is created; the A8 catalog stays at exactly 50. No second
preset identity, renderer, or Store-Appearance/Mega-Menu architecture is
introduced — only existing registered contracts are used.

Mega Menu note: the visible category mega menu is an intrinsic authored feature
of the ``marketplace_search_first`` **header** identity (its partial renders the
real Store category tree). Its truthful, future-Builder-editable source is the
Header selection (``header.marketplace_search_first.v1``). The ``mega_menu``
Store-Appearance family has a single registered component, ``mega_menu.none.v1``
(``virtual:mega_menu:none`` — "no separate mega-menu overlay"), which is the
correct, consistent selection here; the header owns its own category panel.

Guardrails: this service only ever operates on the store handed to it (the
management command scopes that to the fixed ``rasti-mode-demo`` slug). It never
writes commerce truth (price/stock/SKU) and bakes no catalog IDs into settings
— product sections resolve their products at render time from Catalog via
``data_source``.
"""

from __future__ import annotations

from django.db import models, transaction

from apps.storefront_builder import section_registry
from apps.storefront_builder.layout_preset_registry import (
    PresetSectionEntry,
    get_layout_preset,
)
from apps.storefront_builder.models import StorefrontSection
from apps.storefront_builder.services import (
    container_service,
    layout_service,
    preset_service,
)
from apps.storefront_builder.storefront_appearance import persistence as store_appearance_persistence

#: The official Ready Template applied as the Golden baseline. It is applied
#: UNMODIFIED, so ``template_provenance`` and ``template_baseline_snapshot`` both
#: describe the real authored ``fashion_promo_catalog`` DNA. Chosen because it is
#: already the demo seed's applied template and carries the widest commercial
#: fashion vocabulary.
GOLDEN_BASELINE_TEMPLATE_KEY = "fashion_promo_catalog"

#: Golden merchant customizations layered on top of the authored baseline
#: (all existing registered values; the live Draft intentionally diverges here).
GOLDEN_PALETTE_SLUG = "theme-forest-cream"
GOLDEN_HEADER_VARIANT = "marketplace_search_first"
GOLDEN_FOOTER_VARIANT = "premium_columns"
GOLDEN_BOTTOM_NAV_VARIANT = "five_item"

#: A slot-key namespace for the Golden-authored Home sections. Distinct from the
#: baseline template's slot keys — these are merchant-authored sections, not the
#: template's own slots.
_GOLDEN_SLOT_PREFIX = "golden:home:"


def _golden_home_composition() -> tuple[PresetSectionEntry, ...]:
    """The approved 12-section Home in commercial rhythm.

    Editorial impact -> discovery -> campaign -> products(new) -> brand ->
    promo -> products(popular) -> story -> promotion -> collections -> trust ->
    newsletter. Every ``section_key`` is an existing registered section. Only
    neutral, enum-driven settings are provided; no Store IDs, prices, SKUs, or
    inventory are ever written here.
    """
    # The announcement is rendered by the global header itself
    # (``header_config.announcement_enabled`` -> the header partial includes
    # ``_shared/announcement_bar.html``). Adding a separate ``announcement_bar``
    # *section* would render the strip twice (a real defect observed in visual
    # QA), so the announcement lives only in the shell, not the composition.
    return (
        # 1) Editorial hero (store/section HeroSlides render at runtime)
        PresetSectionEntry("hero_banner", {"hero_style": "overlay"}),
        # 2) Quick categories (discovery)
        PresetSectionEntry(
            "category_grid",
            {"display_mode": "circular", "item_limit": 8, "title": "دسته‌بندی‌ها"},
        ),
        # 3) Featured campaign / editorial promotion
        PresetSectionEntry("multi_banner"),
        # 4) New arrivals
        PresetSectionEntry(
            "product_section",
            {
                "data_source": "newest",
                "display_mode": "carousel",
                "title": "جدیدترین‌ها",
                "item_limit": 8,
            },
        ),
        # 5) Brand strip
        PresetSectionEntry(
            "brand_carousel",
            {"display_mode": "carousel", "title": "برندها"},
        ),
        # 6) Promo banners
        PresetSectionEntry("multi_banner"),
        # 7) Most popular / most viewed (uses views_count, a production-written
        #    metric — see ruling R7 in the G1 plan; avoids fabricating Order/
        #    payment/shipping infrastructure just to populate a Home section).
        PresetSectionEntry(
            "product_section",
            {
                "data_source": "most_viewed",
                "display_mode": "grid",
                "title": "محبوب‌ترین‌ها",
                "item_limit": 8,
            },
        ),
        # 8) Story / editorial rail
        PresetSectionEntry("story_rail"),
        # 9) Special offer / promotion
        PresetSectionEntry(
            "product_section",
            {
                "data_source": "discounted",
                "display_mode": "campaign_band",
                "title": "پیشنهاد ویژه",
                "item_limit": 8,
            },
        ),
        # 10) Curated collections
        PresetSectionEntry(
            "collection_tiles",
            {"tile_style": "grid", "title": "کالکشن‌های منتخب"},
        ),
        # 11) Trust / service features
        PresetSectionEntry("trust_features"),
        # 12) Newsletter
        PresetSectionEntry(
            "newsletter",
            {
                "title": "عضویت در خبرنامه",
                "subtitle": "از جدیدترین محصولات و پیشنهادهای ویژه باخبر شوید",
                "button_label": "عضویت",
            },
        ),
    )


def _golden_store_appearance_manifest(draft) -> dict:
    """A schema-v1 Store-Appearance manifest = the authored baseline manifest
    with only the Golden header/footer/bottom-nav family selections overlaid.

    Everything else (hero/card/layout/badge/motion/mega_menu) is inherited from
    the applied baseline, so the commercial DNA of ``fashion_promo_catalog`` is
    preserved and only the merchant-chosen shell regions diverge.
    """
    current = store_appearance_persistence.load_store_appearance_manifest(draft)
    selections = dict(current.selections)
    selections["header"] = f"header.{GOLDEN_HEADER_VARIANT}.v1"
    selections["footer"] = f"footer.{GOLDEN_FOOTER_VARIANT}.v1"
    selections["bottom_nav"] = f"bottom_nav.{GOLDEN_BOTTOM_NAV_VARIANT}.v1"
    return {
        "schema_version": 1,
        "selections": selections,
        "settings": dict(current.settings),
    }


def ensure_golden_view_signals(store) -> int:
    """Give the demo store's products deterministic ``views_count`` so the
    ``most_viewed`` section (and general realism) has data.

    ``views_count`` is a display/analytics metric that IS genuinely written in
    production (``apps.catalog.views.product_detail`` on every view), so seeding
    it for a demo store is legitimate content, not commerce truth. The value is
    derived purely from each product's stable PK, so within a store it is
    reproducible and idempotent — repeated runs recompute the same value and
    never accumulate. (Absolute values differ after a ``--reset`` that rebuilds
    the store with fresh PKs; only the within-store ranking matters here.)
    Returns rows rewritten.
    """
    from apps.catalog.models import Product

    updated = 0
    for product in Product.objects.filter(store=store).order_by("pk"):
        views = 120 + (product.pk * 53) % 3400
        if product.views_count != views:
            product.views_count = views
            product.save(update_fields=["views_count", "updated_at"])
            updated += 1
    return updated


def _customize_golden_draft(draft) -> None:
    """Apply the Golden merchant customizations onto an already-baselined Draft.

    Uses only existing production contracts and — critically — NEVER writes
    ``template_baseline_snapshot`` or ``template_provenance``, so the recorded
    authored baseline stays pure while the live Draft diverges:

      * Store-Appearance manifest (header/footer/bottom-nav) via
        ``persist_store_appearance_manifest`` (Draft-only; also writes the typed
        manifest + the header/footer/mobile-nav selector keys).
      * Identity palette via the validated ``appearance_config`` (mirrors
        ``preset_service``'s palette semantics: set ``palette_slug`` and clear a
        non-merchant-customized ``color_overrides``).
      * Header capability flags (search/account/wishlist/cart, sticky,
        announcement) via ``validate_header_config``.
      * Home section composition via the section registry + container rebuild
        (the same primitives ``apply_preset`` uses), replacing only the Home
        page's sections/containers.
    """
    # 1) Store-Appearance manifest — header/footer/bottom-nav selections.
    store_appearance_persistence.persist_store_appearance_manifest(
        draft, _golden_store_appearance_manifest(draft)
    )

    # 2) Palette + header capability flags (re-read configs after step 1).
    appearance = dict(draft.effective_appearance_config())
    appearance["palette_slug"] = GOLDEN_PALETTE_SLUG
    if not appearance.get("color_overrides_customized"):
        appearance["color_overrides"] = {}
    appearance = layout_service.validate_appearance_config(appearance)

    header = dict(draft.effective_header_config())
    header.update(
        {
            "sticky": True,
            "announcement_enabled": True,
            "show_search": True,
            "show_account": True,
            "show_wishlist": True,
            "show_cart": True,
        }
    )
    header = layout_service.validate_header_config(header)

    draft.appearance_config = appearance
    draft.header_config = header
    draft.save(update_fields=["appearance_config", "header_config", "updated_at"])

    # 3) Home composition — rebuild ONLY the Home page's sections/containers.
    _rebuild_home_composition(draft)


def _rebuild_home_composition(draft) -> None:
    """Replace the Home page's sections with the Golden composition.

    Intentionally mirrors ``preset_service._build_sections_for_page``'s
    registry-lookup → validate-settings → row loop rather than calling it,
    because Golden sections are merchant-authored (their own ``golden:home:``
    slot-key namespace), not template slots. Kept a deliberate, narrow fork; if
    the preset row-building contract changes, revisit this. Touches only the
    Home page's sections/containers — no other page, no baseline metadata.

    The Golden entries deliberately carry no per-container settings, so — unlike
    ``apply_preset`` — no post-rebuild ``StorefrontContainer.settings`` pass is
    needed. The assertion below pins that assumption so a future entry that adds
    ``container_settings`` fails loudly instead of silently dropping them.
    """
    page = draft.get_page("home")
    entries = _golden_home_composition()
    assert all(entry.container_settings is None for entry in entries), (
        "Golden Home entries must not carry container_settings — "
        "_rebuild_home_composition does not write StorefrontContainer.settings."
    )
    assert all(
        not section_registry.get_definition(entry.section_key).hidden_from_library
        for entry in entries
    ), (
        "Golden Home entries must not include a hidden_from_library section "
        "(e.g. announcement_bar, superseded by the header notification bar — "
        "see preset_service._build_sections_for_page's identical gate)."
    )

    rows = []
    for order, entry in enumerate(entries):
        definition = section_registry.get_definition(entry.section_key)
        settings = definition.default_settings() if entry.settings is None else definition.validate_settings(entry.settings)
        rows.append(
            StorefrontSection(
                page=page,
                section_key=entry.section_key,
                order=order,
                settings=settings,
                row_key=entry.row_key,
                row_span=entry.row_span,
                template_slot_key=f"{_GOLDEN_SLOT_PREFIX}{order}",
            )
        )

    page.containers.all().delete()
    page.sections.all().delete()
    StorefrontSection.objects.bulk_create(rows)
    container_service.rebuild_page_from_legacy_rows(page)


#: Which published Home section (by key + occurrence index) owns which seeded
#: media, and how the store-global pool is split across occurrences. The two
#: ``multi_banner`` sections split the 6-banner pool 3/3 so they render DISTINCT
#: content (fixing the duplicate-fallback defect) and each has its own editable
#: rows.
def _ensure_media_asset(row, file_field, asset_field):
    """Backfill a MediaAsset FK from a legacy image file field if missing, using
    the exact in-repo pattern of migration 0021 (reference the same stored file,
    no byte copy). Returns True if a change was made. This is what lets the
    section-scoped row survive the Draft clone (``_clone_section_scoped_media``
    only clones asset-backed placements)."""
    from apps.content.models import MediaAsset

    if getattr(row, f"{asset_field}_id", None) is not None:
        return False
    file_obj = getattr(row, file_field, None)
    if not file_obj:
        return False
    asset = MediaAsset.objects.create(store_id=row.store_id, image=file_obj.name)
    setattr(row, f"{asset_field}_id", asset.pk)
    return True


def _attach_media_to_section(rows, section, *, asset_pairs):
    """Move the given store-global media ``rows`` onto ``section`` (section-scoped)
    and ensure each is MediaAsset-backed. Idempotent: rows already on this
    section are left in place; ``display_order`` is re-sequenced deterministically."""
    for order, row in enumerate(rows):
        changed_fields = []
        if row.section_id != section.id:
            row.section = section
            changed_fields.append("section")
        if row.display_order != order:
            row.display_order = order
            changed_fields.append("display_order")
        for file_field, asset_field in asset_pairs:
            if _ensure_media_asset(row, file_field, asset_field):
                changed_fields.append(asset_field)
        if changed_fields:
            row.save(update_fields=[*dict.fromkeys(changed_fields), "updated_at"])


def _attach_golden_section_media(store, published_version) -> None:
    """Make every Golden Home section that renders media OWN that media
    (section-scoped, MediaAsset-backed) instead of relying on the store-global
    fallback — so the Storefront Builder shows the same items it renders and a
    visibly-rendered item always has a working (non-404) edit path.

    Root cause (G2.1 Defect C): the seed creates store-global (section=NULL)
    HeroSlide/PromotionalBanner/StoryRailItem rows. ``render_service`` falls back
    to them, but the Builder media CRUD is strictly ``section=section`` — so the
    manager showed "0 items" and direct edit URLs 404'd. Attaching the rows to
    their sections removes the fallback ambiguity: render and editor read the
    SAME rows.

    Also fixes the two ``multi_banner`` sections silently sharing one global pool
    (duplicate content) by splitting the 6 banners across them.

    Idempotent + tenant-scoped: operates only on this store's rows and this
    published version's Home sections; re-running converges (rows already on the
    right section stay put, only order/asset backfill is synced). Making each row
    MediaAsset-backed also ensures the Builder's Draft clone
    (``_clone_section_scoped_media``) preserves them, so the editor Draft is
    fully editable.
    """
    from apps.content.models import HeroSlide, PromotionalBanner, StoryRailItem

    home = published_version.home_page()
    ordered = list(home.sections.order_by("order"))

    def sections_for(key):
        return [s for s in ordered if s.section_key == key]

    hero_pairs = [("desktop_image", "desktop_asset"), ("mobile_image", "mobile_asset")]
    story_pairs = [("image", "image_asset")]

    # Reclaim scope (idempotence across re-apply): the Golden setup rebuilds the
    # Home page every run, so section IDs are ephemeral — a prior run's rows are
    # attached to now-archived sections. On ``rasti-mode-demo`` all rows of a
    # media type are Golden demo content, so we reclaim EVERY row of that type
    # for this store (regardless of which section it currently points at) and
    # re-attach it to the current published section. Tenant-scoped by ``store``.

    # HeroSlide -> the single hero_banner section.
    hero_sections = sections_for("hero_banner")
    if hero_sections:
        hero_rows = list(
            HeroSlide.objects.filter(store=store).order_by("display_order", "id")
        )
        _attach_media_to_section(hero_rows, hero_sections[0], asset_pairs=hero_pairs)

    # StoryRailItem -> the single story_rail section.
    story_sections = sections_for("story_rail")
    if story_sections:
        story_rows = list(
            StoryRailItem.objects.filter(store=store).order_by("display_order", "id")
        )
        _attach_media_to_section(story_rows, story_sections[0], asset_pairs=story_pairs)

    # PromotionalBanner -> split the store's whole banner pool across the
    # multi_banner sections so each renders (and owns) a DISTINCT set.
    # Deterministic round-robin keeps the split stable across re-apply.
    banner_sections = sections_for("multi_banner") + sections_for("single_banner")
    if banner_sections:
        banner_rows = list(
            PromotionalBanner.objects.filter(store=store).order_by("display_order", "id")
        )
        n = len(banner_sections)
        buckets = [banner_rows[i::n] for i in range(n)]
        for section, rows in zip(banner_sections, buckets):
            _attach_media_to_section(rows, section, asset_pairs=hero_pairs)


def apply_golden_reference_storefront(store, *, user=None):
    """Establish the Golden Reference Storefront on ``store`` and publish it.

    The correct model (see module docstring): apply the REAL registered
    ``fashion_promo_catalog`` baseline first (honest provenance + authored
    ``template_baseline_snapshot``), then layer the Golden merchant
    customizations on the Draft, then publish.

    Idempotent: any stale Draft is discarded and a fresh one is created, the
    authored baseline is fully re-applied, and the Golden customizations are
    re-applied deterministically — repeated runs converge to the same published
    state without accumulating rows.

    Returns the published :class:`StorefrontLayoutVersion`.
    """
    baseline = get_layout_preset(GOLDEN_BASELINE_TEMPLATE_KEY)
    if baseline is None:  # pragma: no cover - defensive; baseline is always registered
        raise LookupError(
            f"Golden baseline Ready Template «{GOLDEN_BASELINE_TEMPLATE_KEY}» is not registered."
        )

    # G2.1 hardening (Issue 2): the ENTIRE Golden setup must be all-or-nothing.
    # ``layout_service.publish`` has its own (nested) atomic block and commits
    # the new published pointer before media attachment runs; without this outer
    # transaction, a failure in ``_attach_golden_section_media`` would leave a
    # half-set-up Golden version live. Wrapping everything that mutates
    # layout/media/catalog-signals in one outer ``transaction.atomic`` means any
    # failure rolls back to the exact prior state (including the previous
    # published pointer). Nested atomics (publish, apply_preset) are expected and
    # fine — we do NOT rewrite them.
    with transaction.atomic():
        ensure_golden_view_signals(store)

        # Start from a clean Draft so re-runs deterministically re-establish the
        # authored baseline before customizing (converges, never accumulates).
        layout_service.discard_draft(store)
        draft = layout_service.get_or_create_draft(store, user=user)

        # 1) Apply the REAL registered baseline -> honest provenance + authored
        #    template_baseline_snapshot.
        preset_service.apply_preset(draft, baseline)

        # 2) Customize the Draft as a merchant would (does not touch the snapshot).
        _customize_golden_draft(draft)

        # 3) Publish.
        published = layout_service.publish(store, user=user)

        # 4) Make each media-hosting Home section OWN its media (section-scoped,
        #    MediaAsset-backed) so the Storefront Builder shows/edits exactly what
        #    the storefront renders (G2.1 Defect C — no "0 items", no 404 edit
        #    path), and the two multi_banner sections render distinct banner sets.
        #    If this step raises, the whole apply (including the publish above)
        #    rolls back — the prior published version stays live.
        _attach_golden_section_media(store, published)

    return published
