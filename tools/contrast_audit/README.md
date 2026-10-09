# RastiSi contrast audit

A permanent, repeatable accessibility gate for the **whole first-party web product**
(public site, auth, owner portal + onboarding, platform admin, Merchant Admin/Dashboard,
Storefront Builder, and the public storefronts of all Ready Templates).

Contract: **WCAG 2.2 AA** — 4.5:1 normal text, 3:1 large text (≥24px, or ≥18.66px bold), 3:1 for
meaningful icon glyphs and keyboard-focus indicators. Product rule: disabled text that is meant to stay
readable is held to 3:1 although WCAG exempts it. Text over images/gradients must be *deterministic*
(a contained scrim) — see below.

There are two layers; both are needed (a default-page axe scan misses hover/focus regressions and a
static scan cannot see `var()`, `color-mix`, inheritance, alpha or merchant palettes):

| Layer | What | Where | Run |
|---|---|---|---|
| Deterministic | semantic token pairs of every stylesheet, all 50 Ready Template palettes + all 64 registered palettes, dangerous merchant colours, utility maths | `apps/core/tests/test_contrast_utils.py`, `apps/core/tests/test_css_token_contrast.py`, `apps/storefront_builder/tests/test_ready_template_contrast.py` | `python manage.py test apps.core.tests.test_contrast_utils apps.core.tests.test_css_token_contrast apps.storefront_builder.tests.test_ready_template_contrast` |
| Runtime | real Chromium, computed styles, effective backgrounds, every interactive state | `tools/contrast_audit/run_audit.py` | below |

The single WCAG implementation (hex/rgb()/rgba()/`color()` parsing, sRGB→linear, relative luminance,
alpha compositing, ratios, minimal-adjustment helpers) is `apps/core/color_utils.py`. The browser probe
(`probe.js`) only collects raw colours/paint layers; **all maths is done in Python by that same module**,
so the product and the audit cannot disagree.

## How the runtime audit measures

* Every visible text node, input value and placeholder; the foreground is the computed colour × the
  cumulative CSS `opacity` of its ancestors (so opacity-faded text is measured as it is seen).
* The **effective background** is the real paint stack at the text's on-screen position
  (`document.elementsFromPoint`, `pointer-events` forced on so scrims are seen): ancestor colours, absolutely
  positioned overlays, `::before/::after` covers, `linear-gradient` sampled *at the text position*,
  images/video (unknown pixels, bounded by pure black and pure white), alpha composited bottom-up, ending at
  the page canvas (body background propagation included). A transparent own-background never passes a check.
* Verdict categories: `solid`, `gradient`, `image-protected` (a scrim makes it pass over black *and* white
  pixels), `image-unprotected` (fails).
* Large text and icon-only glyphs (arrows, `+`) use 3:1; emoji glyphs are skipped (their colours come from the
  font, not CSS); `disabled` controls use the 3:1 product target.
* **States** per page: rest · hover (each distinct component) · active/pressed · real `Tab` focus traversal
  (subtree contrast + the focus indicator itself must be ≥3:1 against what *surrounds* the control, or be a
  two-tone ring) · toggles (tabs, switches, disclosures, checkboxes/radios, popup triggers → full-page
  re-measure) · scripted actions (empty-form submit → validation errors).
* Counts are de-duplicated: `unique_checks` is distinct (component signature × fg × bg × state class); raw
  measurements are reported separately and are *not* the headline number.

## Running it

Needs the dev server, a seeded store and Chromium (see `scripts/verify_product_entry_ui.py` for the same stack):

```bash
pip install -r requirements.txt playwright            # playwright is already used by tools/ and scripts/
export DJANGO_DEBUG=True DJANGO_SECRET_KEY=dev-only
python manage.py migrate && python manage.py seed_default_plans
python manage.py shell -c "from django.contrib.auth import get_user_model as U; u,_=U().objects.get_or_create(username='09120000001'); u.is_staff=u.is_superuser=True; u.set_password('Testpass123!'); u.save()"
python manage.py seed_rastisi_fashion_demo --owner-username 09120000001
python manage.py runserver 127.0.0.1:8765 --noreload &   # static+templates are cached under --noreload: restart after edits

# suites: public auth portal platform-admin dashboard builder storefront storefront-templates all
python tools/contrast_audit/run_audit.py --suite all --viewport 1366x768 --out /tmp/audit.json
python tools/contrast_audit/run_audit.py --suite dashboard --viewport 390
python tools/contrast_audit/run_audit.py --suite storefront-templates           # all 50 Ready Templates (publishes each to the demo store)
python tools/contrast_audit/run_audit.py --suite dashboard --only dashboard:products --dump badge   # print every measurement of a selector
python tools/contrast_audit/explain.py URL ".selector" [--text STR] [--hover] [--anon]             # which rule/file wins the colour
```

Viewports: `1366x768`, `1440x900`, `390`. Exit status is non-zero while any hard failure remains
(`--rest-only` skips the interaction sweeps). Hosts: `rastisi.localhost` (public/portal),
`<store>.rastisi.localhost` (storefront + admin), `platformadmins.rastisi.localhost` — Chromium resolves
them to loopback through `--host-resolver-rules`.

`storefront-templates` enumerates `layout_preset_registry.list_ready_templates()` (never a hand-kept list),
applies each template to the demo store's draft, publishes it, then audits home (with interaction sweeps),
listing, product page and cart, and reports passing templates.

## How to fix what it finds (root cause first)

Use `explain.py` to find the winning rule, then fix the **token or pairing**, not the symptom:

* hard-coded literal bypassing a token → use the owning token (`--muted`, `--*-ink`, `--rs-muted`, …);
* only one side of a pair changes on hover/active/selected → change both, derive the foreground for the new
  background (`color_utils.state_pair`);
* element `opacity` on a disabled/locked/out-of-stock control → explicit colours (`--disabled-ink/-bg`);
* a brand/merchant colour used as text → the `*-text` variable derived server-side
  (`apps/storefront_builder/accessible_colors.py`), as a fill → the matching `*-fg`;
* text over a merchant image → a contained scrim panel behind the text, not `text-shadow` and not hope;
* link reset beating a component class → zero-specificity resets (`:where(...)`), never `!important`.
