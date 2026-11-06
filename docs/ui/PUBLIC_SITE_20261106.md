# Public site: template drift and oversized internal heroes — 2026-11-06

Branch `ux/platform-merchant-remediation-20261106`. Local only.

## PUBLIC-01 `/design/` advertised more templates than a seller can choose — REPRODUCED and FIXED
`ready_template_rows()` (used by `/design/` and the home shelf) asked the shared catalog service for `SCOPE_PUBLIC` = *every registered Ready Template* (**63**), while the merchant gallery,
the Design Studio gallery and the onboarding Template step use `SCOPE_GALLERY` = the owner-approved subset (**19**, `template_gallery_policy`). 44 templates were publicly visible but not selectable.
That was a documented design decision in the old code ("the gallery restriction limits what a seller may CHOOSE, never what the platform shows publicly"), which the product owner has now reversed.

Fix: the public rows use the same service and the same scope as the galleries (one catalog, no second registry; same key, version and name). Owner overrides on the public page (rename / describe /
categorise / hide / feature) still apply. A registered Ready Template that is not approved for the gallery is not advertised; once approved it appears with no other change.
Hidden / archived / unregistered templates are never listed. Setting `RASTISI_TEMPLATE_GALLERY_RESTRICTED=False` offers everything to both surfaces together.

Tests: `apps/portal/tests/test_public_design_catalog_parity.py` (7; 4 fail without the fix): public set == gallery set (same order), every public template is selectable with the same latest version and name,
non-selectable templates never shown, the page renders exactly those cards and the count label, home shelf, owner hide override, restriction switch.
Updated, deliberately: `test_public_site_v2` "new ready template appears automatically" → appears only once selectable; "lists every real ready template" → lists exactly the selectable ones; the rename test uses an
offered template. The first of these also exposed a test-order artifact (`registry._DYNAMIC` caches per-template public-site fields for the whole process); the test now isolates that cache.

Residual: Platform Admin's public-site editor still lists per-template override sections for all registered templates (including ones that are no longer shown publicly). Harmless, but editing a name there has
no visible effect until the template is approved for the gallery.

## PUBLIC-02 oversized internal heroes — REPRODUCED and FIXED
All internal pages share `.pg-sign` (the privacy/terms/industries pages repeat the markup inline). It had 64px+60px padding and a `clamp(40px,6vw,76px)` headline.
Measured at 1366x768 (real Chromium): 297-378px = **39-49%** of the viewport on the standard pages and **500px = 65%** on `/supported-industries/`.

| Page | Before | After |
|---|---|---|
| /design/ | 332 (43%) | 192 (25%) |
| /features/ | 378 (49%) | 262 (34%) |
| /plans/ | 332 (43%) | 220 (29%) |
| /about/ | 335 (44%) | 154 (20%) |
| /contact/, /help/, /privacy/ | 297 (39%) | 192 (25%) |
| /terms/ | 339 (44%) | 226 (29%) |
| /supported-industries/ | 500 (65%) | 290 (38%) |

Fix: one shared rule — padding 34/30, headline `clamp(28px,3.3vw,44px)`, lead 16.5px, tighter CTA spacing. The home hero is a different component and is untouched; brand colour, typography, header and mobile menu unchanged.
No horizontal overflow at 1366/1440/390 (mobile heroes 169-333px). Guard: `test_public_inner_hero_compact.py` (5, static).
`/supported-industries/` is 290px, slightly above the 180-280 reference, because it carries a two-line lead and a CTA; left as is rather than mechanically shrunk.

## Breadcrumb / title consistency ("Features" on the Design page) — NOT_REPRODUCED
On this code `/design/` has breadcrumb "خانه / قالب‌ها", headline "قالب نقطه شروع است، نه محدودیت", `<title>` "قالب‌ها و طراحی فروشگاه" and active navigation "قالب‌ها" — all consistent; every checked
page (features, plans, about, contact, help, privacy, terms) agrees between breadcrumb, headline, title and active nav. The labels are owner-editable (`design.crumb`, …) in the public-site registry, so a wrong stored override
on a deployment would be a data issue; none exists in the QA database. `/privacy/`, `/terms/` and `/supported-industries/` have no active-nav item (they are not in the header menu — by design).
