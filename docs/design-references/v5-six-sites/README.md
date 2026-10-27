# RastiSi V5 — Complete Six-Site Reference Kit

> **Internal visual/technical evidence, not storefront-ready assets.** No code or database changes are authorized by this package.

This repository folder contains all original HTML/CSS/website images/fonts/other saved files from the user's six ZIP archives (excluding only their 24 screenshot copies that have been relocated *without byte changes*), **24 exact PNG screenshots** and **78 native-width WebP screenshot segments** for comfortable reading. The original ZIPs themselves are **not nested** to avoid redundant copies in Git.

## Start here (Claude Code Web)

1. Read `CLAUDE_READ_ONLY_AUDIT.md`, `SITE_INVENTORY.md`, `manifest.json`, and the **draft** `RastiSi_V5_Six_References_Design_Audit.md`.
2. For **each of the six sites** independently, inspect all four files in `references/<site>/screenshots/original/` (home/product × desktop/mobile), or inspect *every* slice under `screenshots/segments/` in numerical order if huge images are not viewable.
3. Inspect saved HTML, CSS, fonts, and asset dimensions at `references/<site>/capture/`. Do not assume auxiliary `index_1.html` files are product pages: verify document title/content.
4. Produce an exact evidence-backed component inventory for HOME and PDP for EACH site, including global shell, page sections, responsive changes, product cards, PDP gallery, variation selection, purchase panel, sticky/floating elements, breakpoints, typography and semantic colors.
5. Compare each primitive with the CURRENT V5 code and Inspector/renderer wiring; classify `PRESENT_TESTED`, `PRESENT_UNVERIFIED`, `PARTIAL`, `MISSING`, or `UNKNOWN`. Cite file/line paths, distinguish measured CSS from screenshot estimates, and define tests.
6. Do not code yet. Request approval for any engine change. Never create template-specific renderers, databases, or mutation systems; follow R4 canonical contracts.

## What this DOES NOT prove

- Product-page HTML/CSS was not reliably captured (the available saved full HTML documents have homepage titles or embedded auxiliary content). Product screenshots DO exist for every store.
- Browser interaction, computed styles, page viewport CSS units and true pixel-perfect behavior need live browser/evidence; screenshots alone cannot certify them.
- Exact 100% correspondence is not guaranteed even with screenshots. Use visual regression, different viewport widths and two dramatically distinct themes for acceptance.

## Security/IP and branch

**The existing RastiSi GitHub repository is PUBLIC.** Pushing website captures will publish third-party logos, branding, screenshots and artwork. You should review permission and exposure BEFORE running the upload script. A private GitHub repository with access granted to Claude Code Web is preferable when permitted. Do NOT embed any reference-site image/text/logo in customer templates without permission.

Target branch: `feature/v5-design-studio-20261020` (never `main`). Use a FRESH shallow clone so Windows QA worktrees and SQLite/media are untouched. See `WINDOWS_UPLOAD_GUIDE.md` at the ZIP root.

## File map

- `RastiSi_V5_Six_References_Design_Audit.md` — *draft* requirements/audit; should be improved by Claude.
- `CLAUDE_READ_ONLY_AUDIT.md` — new read-only task for Claude.
- `SITE_INVENTORY.md`, `manifest.json`, `SHA256SUMS.txt` — concrete evidence lists and verifiability.
- `references/<site>/capture/` — byte-identical captured source files, preserving site-relative resource paths.
- `references/<site>/screenshots/original/` — exact full-page PNGs.
- `references/<site>/screenshots/segments/` — cropped WebP for deep model visual review.
