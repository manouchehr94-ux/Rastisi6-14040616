# Claude Code Web — READ-ONLY detailed audit for six RastiSi V5 references

Work on the existing feature branch only. Do not change code, tests, templates, migrations, database, files, branches, Git history, or deployment configuration in this stage. Only create a detailed report if explicitly approved (otherwise return it as a response).

## Initialization

- Print `git branch --show-current`, `git rev-parse HEAD`, `git status --short`. Abort if on `main`, or if this evidence folder is unavailable.
- Read `README.md`, `SITE_INVENTORY.md`, `manifest.json` and the existing draft report in this folder.
- For each reference site, independently examine ALL FOUR original PNG screens and/or ALL ordered WebP slices, plus the site's captured HTML/CSS/font resources and image assets. Cite relative paths for every material claim. Do not skim first screen only.

## Deliverable (six detailed blueprints, then unified R4 matrix)

For EACH of AsalBanoo, Dize, khanehshokolati, lilikacosmetics, lilium-gallery, zhimunplus:
1. Full HOME section order top-to-bottom with desktop and mobile differences. List header regions, navigation, announcement, sliders, banners, icon rows, catalog/category/brand carousels, article/footer bands, whitespace, CTA, link states.
2. Full PRODUCT page order, navigation, breadcrumb, gallery/grid and thumbnails, labels/badges, brand/title/rating/price/discount/availability, variants, quantity, actions, delivery/trust/payment/shipping, tabs/accordion/reviews/related products, sticky buy UI, mobile bottom and overlays (only if visually supported).
3. Reproducible design specifications: container breakpoints/max width, section/card width/heights, grids/gaps, fonts (actual font family names from CSS/fonts when possible), type sizes/weights/line heights, borders/radii, shadows, brand/semantic colors, icons, object-fit/aspect ratio, responsive conditions. For EVERY numeric property mark `CSS_EXACT` (path/selector/line) vs `SCREEN_ESTIMATE` (image path & pixel location) vs `UNKNOWN`. Do not invent CSS measurements.
4. List behaviors with `OBSERVED`, `CSS_INDICATED`, `INFERRED`, `UNKNOWN` evidence classes, and identify missing product-page HTML and live interaction captures.
5. Provide a component catalog abstraction capable of building all SIX without template-specific code or hardcoded store-brand assets, showing variation via reusable primitives and presets.

R4 current feature branch: inspect `apps/storefront_builder/section_registry.py`, `services/r4_mutation_service.py`, `services/section_structure_service.py`, `services/preset_service.py`, `layout_preset_registry.py`, `storefront_appearance`, global header/footer registries, Inspector schemas/UI, storefront renderer/templates, theme roles, PDP UI and existing Django/browser tests. The presence of a registry key alone does NOT mean Inspector wiring, roundtrip, or mobile parity passed.

Classify each reference requirement as:
- `PRESENT_TESTED` (test code and preferably browser proof identified)
- `PRESENT_UNVERIFIED` (implementation appears in code but no end-to-end proof)
- `PARTIAL` (show concrete limitations)
- `MISSING` (after code search: no equivalent, propose generic solution)
- `UNKNOWN` (insufficient evidence; say what to inspect)

For all proposed capabilities, specify API/schema/registry responsibilities, Section vs Container vs Region ownership, Inspector editability, global palette inheritance and deliberate override reset, accessibility and RTL, desktop/mobile, Draft/Preview/Publish and Undo/Redo, per-store isolation, rollback, and regression tests. Preserve existing semantics; no parallel engine or independent data/mutation path.

Report a priority-ranked gap list with file paths and line evidence, safe build phases gated on `container.add` real-Windows QA, plus testable PASS/FAIL/NOT EXECUTED acceptance criteria. Report limitations separately. No implementation authorization at this stage.
