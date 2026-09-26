# Storefront Builder V2 — Phase 4 (Header/Footer Composer) Read-Only Gap Audit

**Branch:** `claude/family-visual-fidelity-fix`
**Audited at commit:** `de3161830d03c071cfd9beb2a7fbeff942400e4b` (Phase 3 closure HEAD)
**Method:** Full reads of `apps/storefront_builder/models.py` (header/footer config fields), `views.py` (editor views), `services/layout_service.py` (validators), `services/storefront_context_service.py`, `templates/storefront_shell.html`, `templates/storefront_builder/partials/page_shell_header.html`/`page_shell_footer.html`, all 11 family `header.html`/`footer.html` partials, `apps/content/models.py` (`FooterSettings`, `FooterTrustBadge`, `FooterPaymentLogo`, `Menu`/`MenuItem`, `SocialLink`), `apps/content/context_processors.py`, `apps/core/context_processors.py`, and existing test coverage (`test_views.py::HeaderFooterEditorTests`, `test_page_shell.py`, `apps/content/tests/test_footer_config.py`).

---

## 1. Header editing today

`HEADER_TOGGLE_FIELDS`/`HEADER_CONFIG_DEFAULTS` (`models.py:40-41`): 6 booleans (`show_search`, `show_account`, `show_cart`, `show_wishlist`, `sticky`, `announcement_enabled`) + 1 string (`announcement_text`, ≤300 chars). `storefront_header_editor` (`views.py:910-939`) reads these from POST, validates, writes only to `draft.header_config`. **It is a flat `{field: bool}` dict plus one string — no rows, no components, no ordering, no arrays.**

## 2. Footer editing today

`FOOTER_TOGGLE_FIELDS`/`FOOTER_CONFIG_DEFAULTS` (`models.py:43-47`): 9 booleans, no content fields at all. `footer_config` is **pure gating** — it holds zero content. All real content (about text, contact info, newsletter copy, trust-badge/payment-logo image rows) lives in a completely separate, **non-versioned** `FooterSettings` (`content/models.py:778-861`, one row per Store, `OneToOneField`), `FooterTrustBadge`/`FooterPaymentLogo` (separate Store-scoped tables), edited from an unrelated dashboard screen outside any Draft/Publish cycle. Confirmed directly in the editor's own copy (`footer_panel.html:65`): "متن درباره/تماس، خبرنامه، نشان‌های اعتماد و لوگوهای پرداخت هویتِ زنده‌ی فروشگاه‌اند (نه بخشی از پیش‌نویس/انتشار سازنده)."

## 3. Schema / typed-component model — none exists

`validate_header_config`/`validate_footer_config` (`layout_service.py:75-133`) are pure `{field: bool}` scrubbers against a fixed field list — no rows, no zones, no typed component objects, no ordering. Every "component" is a single global on/off flag wired to one hardcoded position in one hardcoded template partial.

## 4. Version ownership + Draft/Published isolation — confirmed correct

`header_config`/`footer_config` are `JSONField`s on `StorefrontLayoutVersion` (not Store, not StorefrontPage). Both editor views write only to `layout_service.get_or_create_draft(...)`'s result, never `published_version`. `layout_service.publish()` is the only place `published_version` is reassigned, and it's a pure pointer swap.

## 5. All six public page types — same published version, no per-view overrides

`storefront_context_service.build_universal_storefront_context` sets `layout_header_config`/`layout_footer_config` from `version.effective_header_config()`/`effective_footer_config()` identically for every `page_type`. All 6 routes (`apps/catalog/views.py` home/product_detail/listing/collection ×2, `apps/cart/views.py` cart) call this same function; none overrides header/footer independently. `templates/storefront_shell.html` is the single funnel (`{% block header/footer %}` → `page_shell_header.html`/`page_shell_footer.html` when `uses_universal_shell`). **This requirement is already satisfied — no gap.**

## 6. Header/footer rendering is still family-specific — real, confirmed gap

`page_shell_header.html:1` / `page_shell_footer.html:1` both branch: `{% if SHOP_FAMILY %}{% include SHOP_FAMILY.header_variant %}{% else %}...canonical shell...{% endif %}`. `SHOP_FAMILY` resolves from `appearance_config.family_slug` on the **same published version** that owns `header_config`/`footer_config`. Any V2 store that has published with a non-null family (11 exist) gets one of 11 hand-maintained per-family header/footer templates instead of the canonical shared body — each independently re-implementing the same 7+9 boolean toggles by hand (confirmed in `heritage_premium/header.html`, which reads `hc.show_search`/`hc.show_account`/etc. against its own bespoke 3-column DOM). **Header/footer is family-agnostic only for stores with `family_slug=None`.**

## 7. Legacy compatibility boundary — exact fallback order

1. `uses_universal_shell=False` (no `uses_visual_storefront_layout=True` + published version) → `base.html`'s hardcoded footer block, reading `FooterSettings`/`Menu` directly. `footer_config` is not even in scope.
2. `uses_universal_shell=True`, `family_slug=None` → canonical `page_shell_header.html`/`page_shell_footer.html` body, gated by `header_config`/`footer_config`.
3. `uses_universal_shell=True`, `family_slug` set → one of 11 family header/footer variants (§6), still gated by the same `header_config`/`footer_config` keys but via bespoke markup.
4. Within (2) and (3): most footer sub-sections gate on `footer_config` alone; **newsletter uniquely double-gates** on both `footer_config.show_newsletter` (version) **and** the live `FooterSettings.show_newsletter` (legacy) — `page_shell_footer.html:9`.

## 8. Existing component sources — always "all rows for this store", never "these specific rows"

| Model | Store-scoped? | Referenced by ID in config JSON? | Inclusion rule |
|---|---|---|---|
| `Menu`/`MenuItem` | Yes (`Menu.store`, unique per `(store, location)`) | No | Exactly one possible menu per location — structurally cannot be "chosen" |
| `SocialLink` | Yes (`store` FK) | No | All rows matching `show_in_header`/`show_in_footer` for the store |
| `FooterTrustBadge` | Yes | No | All active rows for the store, gated by `FooterSettings.show_trust_badges` |
| `FooterPaymentLogo` | Yes | No | All active rows for the store, gated by `FooterSettings.show_payment_logos` |

All four are confirmed store-filtered **at render time** (not just creation time).

## 9. Responsive/mobile behavior — hardcoded, zero config surface

The mobile hamburger/drawer (`page_shell_header.html`) is unconditional Alpine/CSS wiring, not gated by any config key. Neither `HEADER_CONFIG_DEFAULTS` nor `FOOTER_CONFIG_DEFAULTS` has anything resembling `StorefrontSection.settings["responsive"]`'s per-device visibility. **Real, confirmed gap** — closed in this phase (§10).

## 10. Tenant scoping at render time — confirmed correct

All four component sources above filter by `store=store`/`store_id=...` in their actual render-time queries, not just at creation/`clean()` time. No gap.

## 11. Existing test coverage

`HeaderFooterEditorTests` (10 methods): GET/POST save-to-draft for both, cart-hidden rejection, all-footer-blocks-disabled rejection, HTMX-vs-full-page branching, reachability from the appearance hub. `SharedPageShellTests` (`test_page_shell.py`): same-partial-for-Preview-and-Public, Draft-invisible-until-publish, live-links-real-on-public/inert-in-preview. `apps/content/tests/test_footer_config.py`: `FooterSettings`/badge/logo model+view tests (tenant isolation, validators) — entirely about the legacy live-content models, not `footer_config`. **No existing test targets**: per-component responsive visibility (doesn't exist yet), family-variant parity for header/footer toggles, or an explicit "all six page types render byte-identical header/footer from one version" assertion (implied but not directly tested).

## 12. Real gaps — prioritized for this phase

Confirmed by reading code, not assumed:

1. **No per-component responsive visibility** — real, valuable, closeable without touching family templates or breaking anything. **Closed this phase.**
2. **No typed/strengthened validation architecture** — current validators are ad-hoc dict-scrubbers with no shared, reusable schema-description pattern (unlike `section_registry.py`'s `SectionDefinition`). **Strengthened this phase** (additive, backward-compatible).
3. **Family templates bypass the canonical composer for 11/12 of stores with a family selected** — real, but fixing it means either (a) refactoring 11 hand-maintained templates to consume a shared structured-render function, or (b) accepting the documented compatibility boundary per the master prompt ("family-specific Header/Footer partials may remain temporarily... do not add new family-specific functionality"). **Documented as an accepted, isolated compatibility boundary, not fixed this phase** — refactoring 11 production templates is a large, separate, high-risk undertaking disproportionate to "add responsive settings," and the master prompt explicitly permits the boundary to remain temporarily.
4. **No selection of specific Menu/SocialLink/badge/logo items, no cross-component ordering** — real, but `Menu`'s `UniqueConstraint(store, location)` means there is structurally only ever one menu per location to "select" today; building real multi-menu/ordering support is a materially larger schema change (new FK/M2M surface) than "Header/Footer Composer" needs for this slice, and risks exactly the "generic page-builder-inside-the-header-builder" over-engineering the master prompt warns against. **Not built this phase** — flagged as a legitimate future enhancement, not a Phase 4 blocker (the existing "toggle a fixed named component on/off" model already satisfies "structured composition" per the master prompt's own component list, which never mandates arbitrary multi-instance menus).
5. **Newsletter's double-gate (`footer_config` + legacy `FooterSettings`) is an inconsistency versus badges/logos' single-gate pattern** — investigated per the explicit instruction not to change things merely for symmetry: this predates Phase 3's new functional `newsletter` Home-section block and gates a *different*, still-non-functional footer placeholder ("coming soon" copy, confirmed in Phase 3's own audit of `FooterSettings.show_newsletter`). Changing it now risks altering behavior for stores already relying on the current double-gate to hide the placeholder independently of their general footer toggle state. **Documented, not changed** — this is legacy-placeholder behavior, not a bug in the new composer surface.

## 13. Phase 4 Slice 1 design

Add an optional, additive `responsive` sub-dict to both `header_config` and `footer_config` — a small, explicit allowlist of "responsive-aware component" keys (not a generic per-field mechanism, avoiding over-engineering), each with `hide_on_mobile`/`hide_on_tablet` booleans (desktop is always the baseline — hiding the *entire* header/footer on desktop isn't a real merchant need the way it is for a promotional section). Rendered via the exact same `data-hide-mobile`/`data-hide-tablet` attribute + CSS mechanism already established for section-level responsive visibility (Phase D) — no new CSS system. Applies only to the canonical (non-family) shell partials, consistent with §12 item 3's documented boundary.
