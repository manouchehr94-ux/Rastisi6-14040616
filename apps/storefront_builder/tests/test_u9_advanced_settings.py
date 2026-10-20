"""U9 — Advanced Storefront Settings.

Audit findings:

- The central motion architecture (`MOTION_CHOICES`, `data-sfb-motion`/
  `data-motion` attributes, section-level `motion.style` already wired
  through `responsive_section_wrapper.html`, and a global
  `@media (prefers-reduced-motion: reduce)` override in
  `apps/core/static/css/base.css`) **already existed, fully wired** —
  confirmed by reading the actual CSS and wrapper template, not assumed
  from the phase name. Nothing to build there.
- Real gap found: U4 registered two new section component variants
  (`hero_banner`'s `hero_style`, `collection_tiles`'s `tile_style`) but
  never exposed a merchant-facing control for either — the settings form
  (`partials/section_settings_form.html`) had no `<select>` for them, and
  even if it had, the POST handler (`storefront_section_settings`) builds
  an explicit per-type field allowlist that didn't include either key, so
  a submitted value would have been silently dropped. This is exactly
  U9's "section component variant swap" requirement — closed here.
- `image_text`'s existing `image_position` control and `category_grid`/
  `brand_carousel`'s `display_mode` controls were already present and
  working — confirmed unaffected.
- `header_variant`/`footer_variant` ("global component variant swap")
  were already fully wired (`header_editor.html`/`footer_editor.html`) —
  confirmed, not rebuilt.
"""


from apps.storefront_builder.tests.test_views import StorefrontBuilderViewsTestCase


class MotionArchitectureAlreadyWiredTests(StorefrontBuilderViewsTestCase):
    """Tripwire confirming the audit finding — motion is already centrally
    wired — stays true; not a new feature, a regression guard."""

    def test_reduced_motion_override_present_in_base_css(self):
        import pathlib

        css_path = (
            pathlib.Path(__file__).resolve().parents[2]
            / "core" / "static" / "css" / "base.css"
        )
        content = css_path.read_text(encoding="utf-8")
        self.assertIn("prefers-reduced-motion", content)
