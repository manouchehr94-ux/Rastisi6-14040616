# P5-W4C Final Repaired-Source 704-Cell Recertification — Execution Report

## Provenance

- FINAL_CAMPAIGN_HEAD: `0d2ab09ed40c9df566b9bc551e3065ecf95ce281`
- Production repair head: `6074424b99cd922a28fe3187fef10a53931e535b`
- Final exact source/test head: `c31e07ed8a5cab241e53d1ed7fb905637f1af79e`
- Certified official base: `3a4fe9070584655548bae5a9bb574f3415bbf580` (`origin/feature/phase5-design-expansion`, unchanged throughout)
- Campaign root: `/tmp/rastisi_w4c_final_repaired_0d2ab09e` (external, not committed; fresh — never reused from a prior campaign root)
- Run started: `2026-09-18T20:39:47Z`
- Run finished: `2026-09-18T21:49:32Z`

## Relationship to the old 704 campaign

The previous 704-cell campaign (`CAMPAIGN_HEAD`
`1e4efad80fbfc998cfd05d79658955193e1799d5`) certified a source that a later
rendered visual distinctness closure round found to have 3 genuine
above-the-fold collisions (6 Templates, 3 pairs). That old campaign's
matrix, evidence, and result remain historical for that source head only
and are preserved in git history — **not modified, not reused** by this
round. This report documents the **new, separate** 704-cell campaign run
against the source after the targeted repair (`green_workshop`,
`laleh_play`, `parnian_editorial` bumped v2 -> v3) plus a 3-key static
Gallery preview refresh.

## Ready Template count

50 / 50 (canonical order sourced from `layout_preset_registry.list_ready_templates()`, printed and verified unique before the campaign; recorded in `implementation/42_final_repaired_source_recertification/shard_plan.json`)

## Cell breakdown

- Base cells: 600 / 600 (PASS 600, FAIL 0, BLOCKED 0)
- Theme Tier 1: 50 / 50 (PASS 50, cleanup_verified 50)
- Theme Tier 2: 54 / 54 (27 `warm_boutique` + 27 `beauty_dew`; PASS 54, cleanup_verified 54)
- Total cells: 704 / 704

## Process / invocation counts

- Base+Tier1 shards: 13 (12 shards of 4 keys + 1 final shard of 2 keys), `--w4c-tier2-budget 0` each
- Tier-2 shards: 14 (`--only warm_boutique,beauty_dew --w4c-tier2-budget 4`, 13 shards of 4 cells + 1 final shard of 2 cells)
- Total `manage.py qa_storefront_builder_r4` processes: 27
- Every process was a single real tracked `run_in_background: true` Bash call — never `nohup`/`disown`, never parallel. Each shard's completion was independently verified (exit code, cell count, `matrix._meta.w4c_branch_head_sha`, `duplicate_cells == []`, SQLite backup/restore hash match, no `RateLimitExceeded`, git HEAD/worktree clean) before the next shard was launched.

## Certification truthfulness gate

- PASS: 704
- FAIL: 0
- BLOCKED: 0
- Missing: 0 (704/704 recorded)
- Duplicates: 0
- Accessibility FAIL: 0 (1800 accessibility checks recorded, 0 FAIL)
- Console errors on any cell: 0
- Page errors on any cell: 0
- Failed requests on any cell: 0
- Theme cleanup verified: 104 / 104 (50 Tier-1 + 54 Tier-2)
- `matrix._meta.w4c_branch_head_sha`: `0d2ab09ed40c9df566b9bc551e3065ecf95ce281` (== FINAL_CAMPAIGN_HEAD)
- `matrix._meta.certified_base_sha`: `3a4fe9070584655548bae5a9bb574f3415bbf580` (== official base)
- SQLite restore: PASS on every one of the 27 processes (`pre=d008ecf5...` `post=d008ecf5...` `match=True` each time, plus independently re-verified by this session after each shard)

## Evidence counts

- Home Desktop evidence: 50 / 50
- Home Mobile evidence: 50 / 50
- Representative Listing Desktop: 50 / 50
- Representative PDP Desktop: 50 / 50
- Representative Cart Desktop: 50 / 50
- Tier-2 Theme screenshots: 54 / 54
- Failure screenshots required: 0 (0 FAIL cells) — confirmed no `failures/` directory was populated
- Every recorded screenshot path in `matrix.json` (304 total) verified to exist on disk

## Static Ready-Template Gallery (3-key v3 refresh)

Before this campaign, `green_workshop`/`laleh_play`/`parnian_editorial`
were repaired to v3 but their committed static previews were still v2
(`resolve_real_screenshot()` therefore fell back to the placeholder SVG for
those 3 keys). This round refreshed exactly those 3 keys' real previews:

- `db.sqlite3` backed up (SHA256 `d008ecf5...`) and restored byte-identical after the refresh.
- Captured sequentially (`--only <key>`, one at a time, no parallel captures) via the existing, unmodified `capture_ready_template_previews.py` against a dedicated port-8766 `runserver` (never the W4C certification server on 8765).
- `resolve_real_screenshot()` now resolves a fresh, current v3 real screenshot for all 3 keys.
- Exactly 6 new tracked files: 3× `.webp` + 3× `.meta.json`.
- The other 47 Templates' previews were untouched.

## Rendered visual distinctness

**Rebuilt from this final campaign's own evidence** (not reused from the
earlier closure round, and not a config-signature-only decision — see
`visual_distinctness_matrix.md`/`.json`).

- Rendered PASS: 50 / 50
- NEEDS REPAIR: 0 / 50
- MANUAL REVIEW REQUIRED: 0 / 50
- Config-only PASS decisions: 0 / 50
- `green_workshop` vs `pine_eco`: **DISTINCT**
- `laleh_play` vs `playful_lifestyle`: **DISTINCT**
- `parnian_editorial` vs `silk_editorial`: **DISTINCT**
- `green_workshop` vs `parnian_editorial` (both share the `product_focus`/`beauty_editorial` hero family): confirmed distinguishable from each other via header, layout, product_view, and page background.

## Architecture / duplication audit

CLEAN — see `architecture_duplication_audit.md`. No second registry,
version-history authority, renderer, browser harness, preset-apply
authority, publish authority, Theme owner, Cart implementation,
ProductCard system, Bottom Navigation system, search backend, or tenant
resolver. The visual repair introduced zero Template-name-specific
CSS/render branches.

## Post-campaign gates

`test_w4c_all50_certification_harness` + `test_w4c_accessibility_production_repair`
(166 tests), `test_ready_template_real_previews` (32 tests),
`test_qa_harness_contract` (4 tests), `test_a8_visual_distinctness_repair`
+ `test_w4b_template_curation` (36 tests) — all GREEN. `node --check
tools/storefront_builder_r4_qa/run.mjs` OK. `manage.py check`: 0 issues.
`manage.py makemigrations --check --dry-run`: no changes. `git diff
--check`: OK. The full 3418-test suite was **not** re-run this round —
production/harness/test source is frozen at `c31e07ed8a5cab241e53d1ed7fb905637f1af79e`
and was already accepted clean (0 new/changed failures) against that exact
head.

## W5 status

**NOT STARTED.**
