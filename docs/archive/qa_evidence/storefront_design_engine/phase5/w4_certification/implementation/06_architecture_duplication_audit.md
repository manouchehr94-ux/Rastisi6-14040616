# W4C Implementation Round 1 — Architecture / Duplication Audit

Diff scope verified against approved design head `0399962f1f3bc1a5d4d31c86f1d6add5ff5c13c8`:

```
$ git diff --stat 0399962f1f3bc1a5d4d31c86f1d6add5ff5c13c8 -- apps/ tools/
 apps/storefront_builder/management/commands/qa_storefront_builder_r4.py | 658 ++++++++++++++++--
 apps/storefront_builder/tests/test_w4c_all50_certification_harness.py  | 715 +++++++++++++++++++
 tools/storefront_builder_r4_qa/run.mjs                                 | 327 +++++++++-
 3 files changed, 1618 insertions(+), 82 deletions(-)
```

Exactly the three authorized files: the two harness files (per section 16 of
the plan) plus the one new test module. No other file under `apps/`,
`tools/`, or `migrations/` changed. Zero migrations (`makemigrations
--check --dry-run` reports "No changes detected").

## Duplication sweep

| Check | Command | Result |
|---|---|---|
| Second browser runner | `grep -rl "chromium.launch" tools/**/*.mjs` | Only pre-existing files (`public_w1_qa.mjs`, `public_task5/7/8_qa.mjs`, `w4a_public_shell_qa.mjs`, `w3_design_lab_qa.mjs`, `run.mjs` itself) — no new file created. |
| Second preset-apply path | `grep -n "apply_preset" qa_storefront_builder_r4.py` | One call site: `preset_service.apply_preset_with_checkpoint`, inside `_apply_and_verify_published` — the same canonical function the legacy path and W4B/W4C alike already use. |
| Second publish path | `grep -n "\.publish(" qa_storefront_builder_r4.py` | Three call sites, all `layout_service.publish(store)` — inside `_apply_and_verify_published`, `_theme_cleanup_and_verify`, and `_run_one_theme_cell`'s apply branch. One canonical function, three legitimate callers. |
| Second Theme owner | `grep -n "apply_theme\|clear_theme"` | Only `appearance_authority_service.apply_theme`/`clear_theme` — the same P5-W2 canonical mutation primitives the R4 editor's own `theme.apply`/`theme.clear` mutation types delegate to. No second Theme mechanism. |
| Second cart implementation | inspect `w4cRunCartCell` | Reuses the existing `POST /cart/add/<slug>/` route and `GET /cart/` page — the same routes `public_w1_qa.mjs` already exercises. No new cart logic. |
| Hardcoded OS paths | `grep -n "/var/tmp\|os.sep"` | None. Every W4C path is built with `pathlib.Path` (Python) or derived from a Python-supplied absolute path string via `path.dirname`/`fs.mkdirSync` (Node) — never a hand-built separator. |
| Staff cookie in W4C manifests | inspect `_build_manifest` | The one `manifest["session"] = {...}` assignment is inside `if not w4c_all50:` — structurally unreachable when `w4c_all50=True`. Verified by test case 9 (`test_09_w4c_cell_manifests_never_carry_a_session_key`). |
| `process.exit()` inside the new functions | test case 20, static source-grep | Absent from both `w4cBaseCertification` and `w4cThemeCertification` — only `process.exitCode` is set, in each function's own `finally`. |

## No architecture introduced

- No new Ready Template registry, version registry, section type, Store-
  Appearance family, Theme mechanism, tenant resolver, ProductCard path,
  cart/add-to-cart path, Bottom Navigation system, search backend, or
  browser-rendering/QA authority.
- `capture_ready_template_previews.py` — zero code changes (confirmed by
  `git diff --stat` above listing only the three files); never invoked from
  the new `--w4c-all50` path.
- `layout_preset_registry.py`, `a8_ready_templates.py`,
  `storefront_appearance/*`, `services/appearance_authority_service.py`,
  `services/layout_service.py`, `services/preset_service.py` — read-only
  imports/calls into existing canonical services; zero lines changed.

## One bounded, disclosed naming refinement

The design doc's Theme result/log path pattern
(`<key>__<occasion>__<intensity>__<viewport>`) does not include a tier
discriminator. Because a Tier-1 key's own deterministic occasion assignment
can coincide with one of that same key's 27 Tier-2 combinations when the key
is `warm_boutique`/`beauty_dew` (both are simultaneously in Tier 1 and
Tier 2), that literal pattern can collide for those two keys. This
implementation adds a `tier` segment (`tier1`/`tier2`) to the path
(`_w4c_theme_result_path`/`_w4c_theme_log_path`), which is a strict
extension of the documented pattern (more specific, never less), not a
deviation from the approved architecture. Verified directly by test case 26.
