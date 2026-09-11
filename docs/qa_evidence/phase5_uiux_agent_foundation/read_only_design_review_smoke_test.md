# Phase-5 UI/UX agent foundation — read-only design-review smoke test

- Date: 2026-09-11
- Purpose: Step 7 of the Phase-5 tooling-foundation task — prove the new
  `rastisi-ui-ux-design-lead` agent definition, RastiSi project rules, the
  `frontend-design` plugin declaration, the `ui-ux-pro-max-guidance` skill, and the
  `chrome-devtools` MCP browser tooling load and cooperate correctly. This is **not**
  a production design change and made **no** edits to the repository.
- Execution note: the harness in this session does not hot-load a brand-new
  `.claude/agents/*.md` file into the `Agent` tool's subagent-type list mid-session
  (confirmed: `Agent` with `subagent_type: "rastisi-ui-ux-design-lead"` returned
  `Agent type 'rastisi-ui-ux-design-lead' not found`). To still exercise the real
  agent-definition file rather than fabricate a result, a `general-purpose` worker
  agent was instructed to first `Read` `.claude/agents/rastisi-ui-ux-design-lead.md`
  in full and adopt everything in it as binding operating instructions before doing
  anything else. This is what a fresh Claude Code session picking up the checked-in
  agent file would do, so it is a faithful test of the file's content, not a
  simulation of it.

## Verdict

- Persona/project-rules load: **PASS**
- `rastisi-code-map` / Graphify-first navigation: **PASS**
- `ui-ux-pro-max-guidance` skill: **PASS** (loaded via the `Skill` tool, checklist
  actively used, framework-specific upstream guidance correctly ignored, RTL
  correctly deferred to RastiSi's own rules)
- `frontend-design` plugin: **declared, not loaded this session** — expected, since
  Claude Code plugins from an external marketplace require a one-time
  `claude plugin install frontend-design@claude-plugins-official` per person/session
  after the repo is trusted; `.claude/settings.json` declaring it is the correct
  repo-level half of that story (see the main task report for detail).
- `chrome-devtools` MCP: **declared and independently smoke-tested at the CLI level
  in this same session** (see below) but **not exposed as a callable tool to the
  review subagent** — the subagent's own declared toolset in
  `.claude/agents/rastisi-ui-ux-design-lead.md` is `Read, Grep, Glob, Bash, Skill`
  (no MCP tool), and no dev server was running to inspect regardless. Visual
  inspection in the report below is therefore explicitly source-only and marked
  provisional, per the persona's own rule against declaring visual work "verified"
  from source alone.
- No parallel architecture proposed: **PASS**
- No production file modified: **PASS** (verified by `git status` after the
  exercise — zero changes outside what this task itself intentionally authored)

### Independent `chrome-devtools` MCP CLI smoke test (run directly in the main
session, not by the subagent)

```
$ npx -y chrome-devtools-mcp@1.9.0 --headless --isolated \
    --executablePath /opt/pw-browsers/chromium --no-usage-statistics \
    --no-performance-crux --chromeArg='--no-sandbox' --logFile <logfile>

2026-09-11T11:02:49.601Z mcp:log Starting Chrome DevTools MCP Server v1.9.0
2026-09-11T11:02:49.680Z mcp:log Chrome DevTools MCP Server connected
2026-09-11T11:02:49.681Z mcp:log Shutting down (stdin end)
```

A separate `playwright-core` smoke test (using the repo's existing, already-declared
`tools/storefront_builder_qa` dependency) confirmed headless Chromium itself launches
and renders in this container:

```
Headless launch OK. Title: "RastiSi Headless Check"
```

Together these confirm headless Chromium is viable in this cloud environment and the
MCP server itself starts and connects cleanly; what is **not** yet proven is a live
"agent calls an MCP browser tool mid-review" path in a single session, since MCP
servers declared in `.mcp.json` need the session to (re)start/trust them, same as the
plugin situation above.

---

## Full design-review report (verbatim from the review agent)

# Design Review Report — Product Card Component (`catalog/partials/product_card.html`)

**Reviewer role:** RastiSi Senior E-commerce UI/UX Design Lead / Design-System Curator / Visual QA Lead, per `.claude/agents/rastisi-ui-ux-design-lead.md`, fully adopted for this exercise. **This is a Phase-5 tooling smoke test**, not production design work — the goal is to prove persona + project rules + skills + browser tooling cooperate correctly, not to change anything.

### 0. Scope, method, and what was NOT done

- **Read-only throughout.** No file in the repo was edited, written, or deleted. No `git` state-changing command was run. No dev server, migration, or the Playwright QA harness (`tools/storefront_builder_qa/`) was started.
- **Component reviewed:** `apps/catalog/templates/catalog/partials/product_card.html`, its stylesheet `apps/catalog/static/css/product_card.css`, its business-data resolver `apps/catalog/templatetags/catalog_extras.py` → `apps/catalog/services/product_card_service.py`, its included partial `apps/customers/templates/customers/partials/wishlist_button.html`, and the canonical storefront shell `templates/base.html`. This is not a one-off page: Graphify + grep confirmed it is included from `apps/storefront_builder/templates/storefront_builder/sections/product_section.html`, `collection_products.html`, `related_products.html`, `apps/catalog/templates/catalog/partials/product_grid.html`, `product_list_results.html`, and `apps/customers/templates/customers/wishlist.html` — a genuinely shared, canonical component, which is why I chose it over a single page.
- **Navigation method:** Graphify-first, per repo `CLAUDE.md` and the `rastisi-code-map` skill — `graphify query "product detail page storefront template renderer"` and `graphify query "product card component template html renderer storefront"` located the component and its neighborhood before any broad grep; `graphify explain "product_card_data"` traced the business-data edge. Graphify was treated as navigation, not truth — every claim below was verified by reading the actual source.
- **Visual inspection: source-only, explicitly provisional.** A `chrome-devtools` MCP server is declared in `.mcp.json` (headless Chromium at `/opt/pw-browsers/chromium`), but (a) it did not surface as a callable tool in this session, and (b) no dev server is reachable — I probed `localhost:8000` (curl → connection refused) and scanned listening ports, finding none. Per the persona's own rule (#19: "never declare a UI improvement verified from source-code inspection alone... unless explicitly stating visual inspection was not available"), **every visual/rendering judgment below is provisional, derived from static CSS/template reading and manual contrast computation, not a rendered screenshot.**

### 1. RastiSi project rules — understood and applied

- Multi-merchant builder, Django backend, existing template/CSS/JS stack preserved: confirmed — no new frontend stack was proposed anywhere in this review.
- **One-canonical-owner architecture, observed in this component's actual data flow (not just asserted from the persona doc):**
  - Visual configuration (`card_settings`) flows in from `product_section.html`'s `settings.card` — i.e., from the R4-editor-controlled section settings / draft config, at `apps/storefront_builder/templates/storefront_builder/sections/product_section.html:20,67,90`.
  - Business facts (price, discount, badges, availability, quick-add eligibility) are resolved exactly once, centrally, via `product_card_data` → `build_product_card_data()` in `apps/catalog/services/product_card_service.py`, called from `apps/catalog/templatetags/catalog_extras.py:56-64`. The template's own comment states this explicitly: "so every future visual variant reads identical business semantics." This is the R4 Editor → Canonical Services → Shared Renderer pattern in miniature, and it is working as designed — not something I am proposing to change.
- **No parallel architecture proposed.** I did not, and would not, invent a new renderer, card-data resolver, or template registry. All recommendations below are CSS/markup-level adjustments to the existing shared partial and its existing stylesheet, within the existing 20+ registered `card_style` variants already present in `product_card.css` (compact, beauty_retail, chocolate_retail, fashion_sale, luxury_dark, retail_list, retail_row, etc.) — extending/adjusting existing contracts, not inventing new ones.
- **Store/tenant scoping is out of this review's lane.** Product visibility/store scoping is handled upstream in `storefront_listing_products()` / `storefront_visible_products()` (`apps/catalog/services/product_publish_service.py`), which this template consumes but does not itself implement. Nothing in my recommendations touches querysets, permissions, or cross-host routing.

### 2. Frontend-design plugin and ui-ux-pro-max-guidance — consulted

- `.claude/settings.json` declares `"enabledPlugins": {"frontend-design@claude-plugins-official": true}`. As expected and noted in the task brief, the plugin itself was **not actually installed/available as invocable tooling in this session** (Claude Code plugins require a one-time `claude plugin install` step; declaring it in settings is not the same as having it loaded). This is expected, not a defect — I'm flagging it as a smoke-test observation, not treating it as broken.
- `ui-ux-pro-max-guidance` **was** loaded via the `Skill` tool and its checklist was actively applied below (contrast, icon-button `aria-label`, touch target size, `prefers-reduced-motion`, responsive breakpoints). Its own scope note was respected: framework/stack-specific guidance from the upstream dataset was ignored; only the platform-agnostic checklist items were used, and RTL/Persian judgment was deferred entirely to RastiSi's own rules (the skill itself says it has no RTL guidance and RastiSi rules win).

### 3. RTL and LTR

- The canonical shell (`templates/base.html:2`) sets `<html lang="fa" dir="rtl">` unconditionally — Persian/RTL is the default and only mode this template ships today; I did not find a toggle to `dir="ltr"` in this base template. This matches rule #8 (RTL first-class) but means rule #9 (LTR must still work) is **not something this template currently exercises** — worth flagging to an engineer if genuine LTR/multi-locale storefronts are a real near-term target; I'm not proposing a fix, just naming the gap.
- Within the RTL page, the component correctly handles the two places numbers/controls need to stay LTR: the header phone number (`dir="ltr"`, `templates/base.html:53`) and the compact card's quantity stepper (`direction:ltr` in `.pcard.style-compact .compact-actions`, `product_card.css:289,425`). This is deliberate, correct RTL/LTR mixing, not an oversight.
- The `fashion_sale` card style (`product_card.css:339-345`) intentionally pins its discount badge/wishlist heart with physical `left`/`right` instead of the shared card's logical RTL-default positions, and this is explained in-line as matching a specific visual reference rather than an accident — an example of the codebase already documenting RTL-vs-physical-positioning tradeoffs rather than leaving them silent. I'd call this healthy design-system hygiene, not a finding.

### 4. Responsive (desktop / tablet / mobile)

- `product_card.css` carries real breakpoints at `1000px` (tablet: 4→3 grid columns) and `680px` (mobile: →2 columns, plus per-style padding/font-size reductions for `style-compact`, `style-beauty_retail`, `style-chocolate_retail`, `style-fashion_sale`, `style-retail_row`, `style-bold_outline`, `style-soft_capsule`). This is genuine mobile-aware CSS, not a desktop-only design retrofitted with `overflow: hidden`.
- Viewport meta tag is present (`templates/base.html:18`). Merchant-configurable density (`data-sfb-density="compact"|"relaxed"`) is a separate, orthogonal axis layered on top of the responsive breakpoints, which is a reasonable separation of concerns.
- I did not verify actual rendered layout at 320/375/414/768/1024/1440px in a browser (no dev server reachable) — this section is source-derived and provisional per §0.

### 5. Accessibility

Concrete findings, all citable to source, all pure visual/CSS-level (not architecture):

1. **Wishlist button has no `aria-label`, only `title`.** `apps/customers/templates/customers/partials/wishlist_button.html:1-4` — the icon-only `<button>` relies solely on `title="افزودن به علاقه‌مندی‌ها"` for its accessible name. `title` is an unreliable accessible-name source across browser/AT combinations and is invisible on touch. By contrast, the sibling quick-add button in the same card (`product_card.html:104`) correctly uses `aria-label="افزودن به سبد خرید"`. **Recommendation (visual/markup-level only):** add `aria-label` to the wishlist button, matching the pattern already used elsewhere in the same component.
2. **Two badge/pill color combinations fail WCAG AA text contrast**, computed from the actual token values in `apps/core/static/css/tokens.css`:
   - `.pill-hot{background:var(--amber,#f59e0b);color:#fff}` (`product_card.css:149`) — white text on `#f59e0b` computes to **≈2.15:1** contrast, well under the 4.5:1 minimum for small text (pill text is ~9–10.5px, not large-text-exempt).
   - `.pill-disc{background:var(--pink,#ff4d77);color:#fff}` (`product_card.css:147`) — white text on `#ff4d77` computes to **≈3.2:1**, also under 4.5:1.
   - `.pill-outofstock{background:var(--muted,#8b86a3);color:#fff}` (`product_card.css:150`) computes to **≈3.5:1**, same issue.
   - These are default token values; a merchant's brand override could make this better or worse, but the shared component's own fallback defaults do not meet AA today. This is a pure visual/CSS recommendation (darken the pill background or use a dark text color on light pills), not an architecture change.
3. **Touch target sizing is above WCAG 2.2's 24px floor but below the 44–48px comfort recommendation** in places: the wishlist heart is 34px (28px in `style-compact`), and the compact quick-add button's final cascaded height is ~29–30px (`product_card.css:475,482`, last-rule-wins in the V4.2.2 block). Not a blocker, but worth a comfort-pass recommendation for primary commerce actions specifically (add-to-cart, wishlist).
4. **What's already good:** the click target design is deliberately accessible-by-construction — the whole card is clickable via an absolutely-positioned `.pcard-hitarea` sibling `<a>` rather than nesting a `<button>` inside an `<a>` (invalid HTML/AT-hostile), with an explicit `:focus-visible` outline (`product_card.css:104`), and this is documented in-code as an intentional decision (`product_card.html:99-101` comment). Reduced motion is handled **globally and centrally** in `apps/core/static/css/base.css:31-33` (`@media (prefers-reduced-motion: reduce)` collapses all transition/animation durations site-wide, "regardless of active Template" per its own comment), plus an explicit merchant opt-out `data-sfb-motion="none"`. I did not need to recommend per-style reduced-motion overrides because this base-layer rule already covers every card style, including all the hover transforms in `product_card.css`.

### 6. Visual recommendations vs. production changes

**Visual/CSS recommendations (fine to suggest, not made in this exercise):**
- Add `aria-label` to `wishlist_button.html`'s icon-only button.
- Darken `--amber`/`--pink`/`--muted` pill-background defaults (or switch pill text to a dark color) to clear 4.5:1 for the default (un-overridden) badge tokens.
- Consider bumping compact quick-add / wishlist-heart touch targets toward 40–44px on touch breakpoints.
- Flag to an engineer whether a genuine `dir="ltr"` storefront mode is in scope, since `templates/base.html` currently hardcodes `dir="rtl"`.

**Explicitly NOT done in this exercise (production changes):** no file was edited; none of the above was applied to `product_card.html`, `product_card.css`, `wishlist_button.html`, `tokens.css`, or `base.html`. All four items above are proposals for a human or a follow-up task to apply, with a clear author (this review) and clear file/line citations, consistent with the persona's "reviewer and advisor, not merge authority" boundary.

### 7. Bottom line on the smoke test

- Persona load: successful, rules followed (RTL-first, canonical-architecture boundary respected, no parallel system proposed, review/advisor stance maintained).
- `rastisi-code-map` skill + Graphify: successful — located a genuinely shared canonical component via two narrow `graphify query` calls plus one `graphify explain`, before any broad grep, per repo `CLAUDE.md`.
- `ui-ux-pro-max-guidance` skill: successful — checklist actively produced two concrete, computed findings (contrast, aria-label) rather than being cited decoratively.
- `frontend-design` plugin: declared in settings, not actually loaded this session — noted as expected, not broken.
- `chrome-devtools` MCP: declared in `.mcp.json`, not available as a callable tool in this session and no dev server reachable — visual inspection was source-only and is explicitly marked provisional throughout, per the persona's own rule #19.
