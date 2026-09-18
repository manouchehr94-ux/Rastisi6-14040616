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

VERDICT: **PASS**. Method: structural signature (header, hero-family-or-
intentional-absence, layout, product card style, footer, bottom
navigation) computed from each Template's real `store_appearance`
selections, deliberately excluding palette/font/radius/motion/badge.
50/50 unique signatures across all 50 canonical Templates — 0 structural
collisions, 0 NEEDS REPAIR clusters, 0 unresolved MANUAL REVIEW REQUIRED
findings. Spot-checked against real Home Desktop screenshots for the
largest single-axis (layout-only) collision group and confirmed genuinely
distinct rendered identities beyond configuration labels. See
`visual_distinctness_matrix.md`/`.json`.

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
