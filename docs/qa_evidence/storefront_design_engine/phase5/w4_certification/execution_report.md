# P5-W4C Final All-50 Certification Campaign — Execution Report

## Provenance

- Full CAMPAIGN_HEAD: `1e4efad80fbfc998cfd05d79658955193e1799d5`
- Final evidence HEAD (this report's own commit's parent chain): `ee469a3579db0b6269b50726ac3517eb5cf79fe3`
- Certified official base: `3a4fe9070584655548bae5a9bb574f3415bbf580` (`origin/feature/phase5-design-expansion`, unchanged throughout)
- Campaign root: `/tmp/rastisi_w4c_final_1e4efad8_attempt2` (external, not committed)
- Discarded root (preserved, not certifiable): `/tmp/rastisi_w4c_final_1e4efad8` — Attempt 1, killed mid-shard-02 by an unsafe `nohup`/`disown` detachment before its own DB-restore step ran (see "Attempt 1" below)
- Run started (Attempt 2): `2026-09-18T12:53:59.677746`
- Run finished (Attempt 2): `2026-09-18T14:26:12.557749`

## Attempt 1 (preserved, not certifiable)

Shards 02-13 were first launched via a detached (`nohup ... & disown`)
batch script on the assumption it would survive independently of the
launching tool call. The sandbox instead tore down the whole process
group when that tool call ended, killing shard 02 mid-run — before its
own `finally`-style DB-restore/cleanup step executed. This left
`db.sqlite3` mutated relative to its own pre-shard-02 safety backup
(verified via SHA256 mismatch: current `dc7d358f...` vs. backup
`d008ecf5...`), and `matrix.json` in that root ended up with 3 partial,
unverified template entries (`playful_lifestyle`, `utility_catalog`,
`editorial_jewelry` — 12 cells each — the 4th shard-02 key,
`dark_digital`, was mutated via drift-repair but never got any cell
written before the kill). Per Independent Architect instruction: the
root is preserved exactly as-is at `/tmp/rastisi_w4c_final_1e4efad8`,
never edited, never resumed, and explicitly excluded from certification.
`db.sqlite3` was restored from that shard's own verified backup
(hash-confirmed equal) before Attempt 2 began.

## Ready Template count

50 / 50 (canonical order sourced from `layout_preset_registry.list_ready_templates()`, printed and verified unique before the campaign)

## Cell breakdown

- Base cells: 600 / 600
- Theme Tier 1: 50 / 50
- Theme Tier 2: 54 / 54
- Total cells: 704 / 704

## Process / invocation counts (Attempt 2, the certified run)

- Base+Tier1 shards: 13 (12 shards of 4 keys + 1 final shard of 2 keys), each a single real tracked `run_in_background` `manage.py` process — never detached, never parallel
- Tier-2 shards: 14 (`--only warm_boutique,beauty_dew --w4c-tier2-budget 4`, 13 shards of 4 cells + 1 final shard of 2 cells)
- Total `manage.py qa_storefront_builder_r4` processes: 27
- Node invocations: 8 per full 4-key Base+Tier1 shard, 4 for the final 2-key shard, 1 per Tier-2 shard-worth of missing cells actually run — consistent with the harness's own per-shard reporting; exact per-cell provenance is recorded in `matrix.json`

## Certification truthfulness gate

- PASS: 704
- FAIL: 0
- BLOCKED: 0
- Missing: 0 (704/704 recorded)
- Duplicates: 0
- Accessibility FAIL: 0
- Console errors on any PASS cell (favicon excluded, no new exclusion created): 0
- Page errors on any PASS cell: 0
- Failed requests on any PASS cell (favicon excluded): 0
- Theme cleanup verified: 104 / 104

## Evidence counts

- Home Desktop evidence: 50 / 50
- Home Mobile evidence: 50 / 50
- Representative Listing Desktop: 50 / 50
- Representative PDP Desktop: 50 / 50
- Representative Cart Desktop: 50 / 50
- Tier-2 Theme screenshots: 54 / 54
- Failure screenshots required: 0 (0 FAIL cells)

## Visual distinctness

**SUPERSEDED.** The structural-signature-only method below was the first
pass; per Independent Architect correction ("Rendered Visual Distinctness
Closure" round), it did not satisfy the binding rendered-evidence contract
and was replaced by a review grounded in the actual Home Desktop+Mobile
captures. See "Rendered visual distinctness closure" below for the
current, authoritative verdict.

<details><summary>Original (superseded) structural-signature pass</summary>

VERDICT: PASS. Method: structural signature (header, hero-family-or-
intentional-absence, layout, product card style, footer, bottom
navigation) computed from each Template's real `store_appearance`
selections, deliberately excluding palette/font/radius/motion/badge.
50/50 unique signatures across all 50 canonical Templates — 0 structural
collisions. Spot-checked against real Home Desktop screenshots for the
largest single-axis (layout-only) collision group.

</details>

## Rendered visual distinctness closure (authoritative)

**VERDICT: NEEDS REPAIR.** Every one of the 50 Templates' real Home
Desktop (1440x900) and Mobile (390x844) captures in `home_gallery/` was
directly viewed (contact sheets covering all 50 on both viewports, plus
individual full-resolution re-fetches for every Template in a 6+-member
hero-component family and every algorithmically-detected exact match on
header+hero+layout+product_view+bottom_nav). Configured selections are
retained only as supporting metadata, per instruction.

- Reviewed Desktop: 50/50. Reviewed Mobile: 50/50.
- Rendered PASS: 44/50.
- MANUAL REVIEW REQUIRED: 0.
- NEEDS REPAIR: 6/50 (3 pairs): `pine_eco`/`green_workshop` (Mobile
  screenshots are byte-identical (same SHA256 blob); Desktop screenshots are
  different blobs but were judged visually indistinguishable above the
  fold), `playful_lifestyle`/`laleh_play`
  (identical arch-hero composition/photos/copy, palette-only difference),
  `silk_editorial`/`parnian_editorial` (identical hero panel, header-color/
  page-tone-only difference).
- Config-only PASS decisions: 0.

Important finding recorded: hero photography/headline/CTA copy is
Store-level demo content shared by every Template using the same hero
component (e.g. all 7 `hero.editorial_split.v1` Templates render the
literal same jacket/jacket/shoe photos and headline) — expected given one
shared demo catalog, not itself a defect, but it means real distinguishing
power for a shared-hero cluster comes from header structure, secondary-
section composition, and Mobile bottom-navigation, not hero photography.

Footer limitation recorded: all 50 captures are single-viewport screenshots
at initial load; the footer is below the fold on every Template and was
never reached by any of the 50 captures. `observed_footer` is `NOT_VISIBLE`
for all 50 rather than inferring an uncaptured appearance.

Per this round's binding rule, `needs_repair_count > 0` downgrades the W4C
final certification status to **NEEDS REPAIR** on visual-distinctness
grounds. The 704/704 real browser certification result itself (FAIL=0,
BLOCKED=0, accessibility FAIL=0, 0 unexpected errors, Theme cleanup
104/104) is unaffected and remains frozen/accepted. See
`visual_distinctness_matrix.md`/`.json` (now containing per-Template
`observed_*` fields, evidence paths, and rendered verdicts for all 50) and
`failure_summary.md` for full detail.

## Static Ready-Template Gallery staleness

- STATIC GALLERY STALE KEYS: 50 / 50 (8 version-mismatched: `premium_leather`, `dense_marketplace`, `warm_boutique`, `fashion_promo_catalog`, `playful_lifestyle`, `utility_catalog`, `editorial_jewelry`, `dark_digital`; 42 never previously captured at any version)
- STATIC GALLERY REFRESH: **COMPLETE**
- Refreshed via the existing, unmodified `capture_ready_template_previews.py`, against a separate `runserver` on port 8766 (never the certification server), one key at a time, sequentially
- DB PRE-REFRESH SHA256: `d008ecf54d4ad8e73c0aa44a443d1ceeb87f958a0d5c4097b7d831dea1b6efad`
- DB BACKUP SHA256: `d008ecf54d4ad8e73c0aa44a443d1ceeb87f958a0d5c4097b7d831dea1b6efad` (`/tmp/rastisi_gallery_refresh_db_backup_20260918T121642Z.sqlite3`)
- DB POST-RESTORE SHA256: `d008ecf54d4ad8e73c0aa44a443d1ceeb87f958a0d5c4097b7d831dea1b6efad`
- DB RESTORE MATCH: **YES**
- Post-refresh freshness re-check: 50/50 keys resolve fresh via `resolve_real_screenshot`
- `capture_ready_template_previews.py` itself: unmodified

## SQLite restore results

PASS for every one of the 27 certification `manage.py` processes in
Attempt 2 (each process's own `pre=...post=...match=True` log line,
independently re-verified against `sha256sum db.sqlite3` after every
single shard before the next one started) and for the Gallery refresh's
before/after backup-restore cycle.

## Official base SHA

`3a4fe9070584655548bae5a9bb574f3415bbf580` — unchanged throughout.

## W5 status

NOT STARTED. `gallery_index.md` is recorded as a W5 handoff artifact only.

## Source/harness changes

None. `qa_storefront_builder_r4.py`, `run.mjs`, the Ready Template
registry, `preset_service.py`, `layout_service.py`, and all production
rate limits are byte-identical to `CAMPAIGN_HEAD`. Every commit in this
round touches only `docs/qa_evidence/...` and
`apps/storefront_builder/static/ready_template_previews/...`.
