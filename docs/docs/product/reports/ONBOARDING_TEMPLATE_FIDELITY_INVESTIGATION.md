# Onboarding: selected Ready Template vs delivered storefront (investigation)

**Question.** "The storefront delivered after onboarding looks nothing like the Ready Template I selected." Which layer is wrong?

## Root cause (classification: B + A-lite)

* **B — the template IS applied and published exactly; the delivered storefront differs because the new Store is empty.**
  A Ready Template is mostly *data-driven composition*: Hero slides, the category rail and the product rows/wall read
  merchant-owned rows. A freshly onboarded Store has none of them, so the public renderer (correctly, by design —
  `render_service.hide_empty_public_sections` + sections that render nothing without slides/categories) delivered only the
  template's **shell** (palette, header variant, footer variant) and an almost blank body.
* **Preview misrepresentation.** The canonical screenshots under `apps/storefront_builder/static/ready_template_previews/` are
  captured by `capture_ready_template_previews` from the fully populated **Rasti Mode Demo** store (`capture_source:
  rasti-mode-demo` in every `*.meta.json`: 50 products, 150 images, hero slides, banners, stories). Onboarding showed them with
  no hint that the products/photos/banners are demo content a new Store does not receive.
* **A-lite — selection UX was correct but weak.** The click target and server authority were fine (preview never selected;
  the POST carried exactly `template_key`), but the selected state was a thin border + small check, the CTA never named the
  template, the large preview offered no way to choose, and Review showed the template at the same weight as an empty row.
* **Not a bug:** Draft and Published provenance/composition matched the catalog exactly for every tested template; the public
  renderer is faithful — with catalog data the same published template renders identically to the canonical screenshot.

## Evidence (fresh owner, real browser, anonymous isolated context)

| Template | Draft provenance | Published provenance | Empty store (before) | Same store populated |
|---|---|---|---|---|
| `dark_digital` v3 «پالس نئون» | key/version/sections/palette/header/footer == catalog | same Draft published, unchanged | dark shell + newsletter box only | identical to canonical |
| `warm_boutique` v3 «کارگاه لاله» | == catalog | == catalog | shell + newsletter | identical to canonical |
| `dense_marketplace` v3 «بازار مکس» | == catalog | == catalog | shell + trust strip | identical to canonical |

What survived in the empty Store: palette, typography, header variant, footer variant, static sections (newsletter, trust
strip). What vanished: Hero, category rail, every product row / catalog wall (they read merchant rows).

## Decision (no fake data, no second renderer)

1. **First-run structural placeholders** (`first_run_placeholder_service`): a non-persistent render-time substitution, only for
   the public **home** of a modern-portal Store (`onboarding_required_at` set) that has **no storefront-listable product yet**.
   Empty hero/slider, category rail and product rows/wall render a neutral, honestly worded placeholder styled only with the
   selected template's own `--theme-*` palette and `--radius`. No Product/Category/HeroSlide/Banner/Order/Customer is ever
   created. The first listable product ends the state and the normal data-driven rules apply. Legacy Stores are untouched.
2. **Truthful labels**: the Template step, its large-preview dialog and Review state that previews use sample content and that
   the Store is first published without products.
3. **Unmistakable selection**: each card has an explicit «انتخاب این قالب» / «✓ انتخاب شده» affordance and a «محتوای نمونه» tag;
   the selected card has a thick border + tint; a sticky bar shows «قالبِ انتخاب‌شده: «X»» and the CTA reads «اعمالِ «X» و
   ادامه»; the large preview says it does not select and has its own explicit «انتخاب این قالب». Server authority unchanged.
4. **Review**: the chosen template is shown prominently (name, version, larger screenshot, sample-content explanation).

## Known remaining debt

* The shared newsletter section renders a plain white email input regardless of palette (pre-existing; visible on dark
  templates). Not part of this change.
* Static sections that carry no merchant text (e.g. `image_text`, `testimonials` in some templates) render nothing until the
  owner edits them; they are template-authored content, not catalog data.
