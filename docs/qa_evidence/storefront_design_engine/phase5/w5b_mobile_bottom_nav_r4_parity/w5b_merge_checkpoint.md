# P5-W5B — Merge Checkpoint

This is evidence only, recorded after PR #14 was merged per the Independent
Architect's final merge verdict (CRITICAL 0, IMPORTANT 0, BLOCKING MINOR 0).

## Merge record

- **PR:** [#14](https://github.com/manouchehr94-ux/Rastisi6-14040616/pull/14)
- **Approved integration base:** `e8a0a33841cf1eff289f76588d95491558ba9348`
  (`feature/phase5-design-expansion`, unchanged since W5B authorization
  through the entire engagement).
- **Approved PR head:** `b8b4a563ae43827b37cba81f555caf3e2e282aba`
- **Production source head:** `0359851bd262d501fcbdbf4dceed238aa5b7c8a3`
  (`feat(phase5): expose mobile bottom navigation in R4` — no production
  file changed in any commit after this one, through either browser-QA
  repair round).
- **Exact-source regression head:** `5ce8bc953ab2ffeaa7bcd094716bd048d4bbff22`
  (the commit the 3502-test exact-source full regression was run against).
- **Merge commit SHA:** `5e5d0180d1efbd7aec351891e4049df1715b2b50`
- **Merge method:** normal merge (two parents: `e8a0a338` and `b8b4a563`) —
  not squashed, not rebased, not forced.
- **Post-merge integration branch:** `feature/phase5-design-expansion`
- **PR state after merge:** `state: closed`, `merged: true`.

## Ancestry verification

```
git merge-base --is-ancestor e8a0a33841cf1eff289f76588d95491558ba9348 5e5d0180d1efbd7aec351891e4049df1715b2b50   → base IS ancestor
git merge-base --is-ancestor b8b4a563ae43827b37cba81f555caf3e2e282aba 5e5d0180d1efbd7aec351891e4049df1715b2b50   → PR head IS ancestor
git merge-base --is-ancestor 0359851bd262d501fcbdbf4dceed238aa5b7c8a3 5e5d0180d1efbd7aec351891e4049df1715b2b50   → production source head IS ancestor
git merge-base --is-ancestor 5ce8bc953ab2ffeaa7bcd094716bd048d4bbff22 5e5d0180d1efbd7aec351891e4049df1715b2b50   → regression head IS ancestor
```

All four PASS.

## Source integrity — no merge-resolution change

The base branch had not moved since W5B authorization (`e8a0a338` was still
`origin/feature/phase5-design-expansion`'s HEAD immediately before merging),
so this was a conflict-free, fast-forwardable merge:

```
git diff b8b4a563...5e5d0180            → empty (merge commit tree == approved PR head tree, byte-for-byte)
git diff 5ce8bc95...5e5d0180 -- apps/   → empty (certified app/test tree == merged tree, byte-for-byte)
```

No merge-resolution change touched any production or test file. This
proves the merge did not alter the exact source/test tree that received
the 3502-test exact-source regression.

## Architecture summary (carried forward from the certified source)

- `GLOBAL_MOBILE_NAV_REGION` remains the sole canonical registry for Bottom
  Navigation — no second registry, no parallel authority.
- Registered variants: **9** (`hidden`, `luxury_floating_cart`, `four_item`,
  `five_item`, `raised_cart`, `floating_dock`, `glass_dock`,
  `minimal_icons`, `wide_cart`).
- New variants: **0**. New renderers: **0**. New mutation types: **0**
  (`footer.update` remains the single entry point). Migrations: **0**
  (`mobile_nav_variant` was already a key inside the existing
  `footer_config` JSONField).

## R4 parity (production behavior, certified at source head `0359851b`)

- `mobile_nav_variant` exposed as a merchant-facing control in R4 Global
  Design ("ناوبری پایین موبایل").
- Registry-driven options: **9/9**, derived from
  `global_region_registry.list_global_variants(GLOBAL_MOBILE_NAV_REGION)` —
  never a second hardcoded list, in production code or in the QA script.
- Existing `footer.update` mutation reused unmodified as the entry point.
- Existing `layout_service.validate_footer_config()` reused unmodified as
  the single validator boundary.
- Existing `appearance_authority_service.apply_footer_variant()` reused
  unmodified for the typed-manifest sync.
- Typed `selections["bottom_nav"]` sync: **PASS**.
- Sibling `footer_variant` selection preserved: **PASS**.
- Unrelated Store Appearance families (header, hero, product_view, card,
  badge, theme, template, palette, ...) preserved: **PASS**.
- Stale-write protection (existing `base_revision` boundary, unmodified):
  **PASS**.
- Undo: **PASS**. Redo: **PASS**.
- Draft Preview resolution: **PASS**.
- Public unchanged before Publish: **PASS**.
- Public reflects the change after Publish: **PASS**.
- `hidden` variant (true no-op renderer, safe default): **PASS**.
- Tenant isolation (mutation never touches a foreign Store's Draft):
  **PASS**.

## Browser certification reference (not rerun post-merge — see gates below)

Round-2 (Independent Architect browser-evidence repair) result, reused as
the certified reference:

- **Browser QA: 23/23 PASS.**
- Draft mobile width: `390` (`window.innerWidth` inside the Draft Preview
  iframe, real mobile device mode).
- Draft nav: `display: block`, bounds `370×64` (non-zero, computed-style
  and DOM-verified, not source-HTML string matching).
- Public mobile width: `390` (real `{width: 390, height: 844}` Playwright
  viewport context on the public storefront page).
- Public nav: `display: block`, bounds `370×64`.
- Footer variant: `legacy_default` → `legacy_default` (exact before/after
  equality).
- Registry: expected `9`, actual `9`, missing `[]`, unexpected `[]`.
- Screenshots (evidence directory, preserved from the repair round):
  - `screenshots/01-draft-preview-mobile-four_item.png`
  - `screenshots/02-public-mobile-four_item.png`
  - `screenshots/03-fresh-draft-hidden-mobile.png`

The round-2 browser-evidence repair changed **only** the QA script
(`tools/storefront_builder_r4_qa/w5b_mobile_bottom_nav_r4_parity_qa.mjs`)
and evidence/docs files — it did not alter any production or Django-test
source file. Confirmed by `git diff --check` between the pre-repair PR
head (`46b5dba4`) and the post-repair approved PR head (`b8b4a563`) being
limited to `tools/storefront_builder_r4_qa/...` and
`docs/qa_evidence/.../w5b_mobile_bottom_nav_r4_parity/...` paths only.

## Full regression certification reference (not rerun post-merge)

- **Exact-source full suite: 3502 tests, 30 historical failures, 2
  historical errors, 1 skip** — exact match to the accepted W5A baseline
  (3478/30/2/1), with the 24 additional tests being W5B's own (all pass).
- **0 new failure/error identities, 0 missing, 0 changed reasons** — all
  32 matched failure/error blocks byte-for-byte identical to baseline,
  including full tracebacks (`full_suite_identity_comparison.md`).
- **704-cell Ready Template campaign: NOT RUN** — renderer/Ready-Template
  architecture untouched by W5B at any point (0 renderer/registry/template
  changes in the production diff).
- **Architectural duplication: 0** — no second Bottom Nav registry,
  renderer, mutation type, read projection, or write path anywhere in the
  chain.

## Post-merge lightweight gates (run fresh, at the merged integration HEAD)

Per the merge directive: the exact W5B source was already fully certified
at `0359851b`/`5ce8bc95`, the later commits were evidence/docs (and one
QA-script-only repair) on top of it, the integration base had not moved,
and the merge was conflict-free — so the 3502-test full suite and the
704-cell campaign were **not** rerun. Only focused post-merge
verification, run with no competing test/server process:

| Gate | Result |
|---|---|
| `python manage.py test apps.storefront_builder.tests.test_phase5_w5b_mobile_bottom_nav_r4_parity --settings=shop_core.settings -v 2` | **24/24 PASS** (`Ran 24 tests in 36.404s`, `OK`) |
| `python manage.py check --settings=shop_core.settings` | PASS — "System check identified no issues (0 silenced)." |
| `python manage.py makemigrations --check --dry-run --settings=shop_core.settings` | PASS — "No changes detected" (0 migrations) |
| `git diff --check` | PASS — clean |

- **704-cell W4C/W5 campaign:** NOT RUN (not required — no renderer/Ready
  Template output touched by W5B at any point).
- **W5C:** NOT STARTED — no W5C source, docs, branch, or plan exists in
  this repository as of this checkpoint.

## Worktree / branch state at checkpoint time

- Local branch: `feature/phase5-design-expansion`.
- Local HEAD: `5e5d0180d1efbd7aec351891e4049df1715b2b50` (== remote
  `origin/feature/phase5-design-expansion`, fast-forwarded cleanly, no
  reset/rebase/force).
- Worktree: clean.
