# W5C — Independent Code Review

Review scope: the W5C diff at the point of first implementation (before
the fixes documented below), run via the repository's `code-review` skill
at effort level `high`, over `template_gallery.html`,
`template_gallery_preview.js`, and the new test file, plus manual
verification against every item the directive's §24 called out by name.

## Automated pass result (first implementation)

**4 findings, all real, all fixed.** No CRITICAL/IMPORTANT split was
reported by the tool itself; by severity all four are genuine correctness/
accessibility bugs that would have shipped visible defects, so all four
are treated as blocking and were fixed before this document's final
state.

| # | Finding | Fix |
|---|---|---|
| 1 | `storefront_template_live_preview` was never given `@xframe_options_sameorigin`; Django's global `X-Frame-Options: DENY` default would make every browser refuse to render it inside the new `<iframe>` — the dialog would open but stay blank for all 50 templates, both data modes. | Added `@xframe_options_sameorigin` to the view, mirroring `storefront_preview`'s own existing, identically-justified override. See `preview_authority_chain.md`. |
| 2 | The document-level click handler called `evt.preventDefault()` unconditionally for any `[data-tpl-preview-trigger]` click, and the diff dropped the triggers' previous `target="_blank" rel="noopener"` with no fallback — a Ctrl/Cmd/Shift-click (native "open in new tab") was silently cancelled, and if the JS ever failed to load, a plain click would now navigate the CURRENT tab away instead of degrading to "open in a new tab" as before. | The click handler now checks `evt.ctrlKey \|\| evt.metaKey \|\| evt.shiftKey \|\| evt.button === 1` and returns early (native browser behavior proceeds) before calling `preventDefault()`. The no-JS/JS-failure case still degrades gracefully via the trigger's own real `href` (same-tab navigation to the canonical URL — an accepted, directive-permitted fallback, not a regression). |
| 3 | `setDataSource()` unconditionally reassigned `frame.src` even when the requested mode was already active, forcing an unnecessary full iframe reload (visible flash, lost scroll position) on a redundant click. | Split into `setDataSourceButtonState()` (button/state only, no side effect) and the click handler now short-circuits when `mode === state.dataSource`; `openFromTrigger()` still always calls `loadCurrentUrl()` once, since a fresh open/retarget is never a "no-op" case. |
| 4 | The dialog declared `role="dialog" aria-modal="true"` but only Escape was handled — no focus trap, so `Tab`/`Shift+Tab` could cycle focus onto the 50 Gallery cards' links/buttons hidden behind the opaque backdrop while the dialog was still visually open. | Added a `Tab`/`Shift+Tab` handler (gated on `isOpen()`) that wraps focus between the dialog's first and last focusable elements. Known, documented nuance: focus that moves INSIDE the iframe's own same-origin document isn't interceptable from the parent frame's listener — see `accessibility_review.md`. |

## Re-review after fixes

A second pass over the corrected diff found **zero further issues** in
the same three files.

## Manual verification against the required checklist (§24)

| Item | Finding |
|---|---|
| Second Preview route | None — `dashboard:storefront-builder-template-live-preview` is the only route referenced anywhere in the new markup/JS; grep of `template_gallery_preview.js` for `fetch(`/`XMLHttpRequest`/`.open(` returns nothing. |
| Second renderer | None — the iframe's `src` is always one of the two `{% url %}`-built canonical URLs; the JS never fetches or constructs HTML. |
| `srcdoc`/fake storefront | None — `frame.src` is always a real URL; `srcdoc` never appears in the diff. |
| Duplicated Ready Template definitions | None — `REGISTERED_READY_TEMPLATE_KEYS` in the test file is derived from `layout_preset_registry.list_ready_templates()`, never hand-written; the template markup iterates the same `template_cards` context the view already built. |
| Hardcoded Store identity | None — every URL is built server-side per-card from `preset.key` alone; the JS never reads/writes a store id. |
| Tenant leakage | None — `GalleryPreviewTenantIsolationTests.test_query_string_store_hints_are_ignored_in_merchant_preview` proves a bogus `store_id`/`store`/`tenant_id` in the query string is ignored; `_resolve_store(request)` is untouched. |
| Preview causing Draft writes | None — see `non_mutation_proof.md`. |
| Apply path duplication | None — the existing `<form action="{% url 'dashboard:storefront-builder-apply-preset' %}">` is byte-for-byte unchanged; the JS defines no `apply`-named function or endpoint. |
| Screenshot-staleness regression | None — `template_preview_service.resolve_real_screenshot()`/`resolve_gallery_thumbnail()` are untouched; the thumbnail `<img>`/SVG fallback markup is unchanged (only the WRAPPING `<a>`'s href/attributes changed, per §7's explicit requirement). |
| Two/three iframes instead of one | None — `test_exactly_one_preview_iframe_in_the_dialog_markup` counts exactly one `<iframe` and one `data-tpl-preview-frame` in the rendered page, regardless of the 50 cards. |
| Persisted device state | None — `state.device`/`state.dataSource` are plain closure variables; no `localStorage`/`sessionStorage`/cookie/query-param write exists anywhere in the JS. |
| Duplicated Desktop/Tablet/Mobile application authority | None in the "shared runtime state" sense — see the plan's §11: the width contract (1200/768/390) is a documented design-constant convention, not a second authority; each controller owns its own DOM/state independently. |
| Inaccessible modal | Fixed (finding #4 above) — see `accessibility_review.md`. |
| Focus loss | Fixed (finding #4) — focus trap added; focus-restore-to-trigger was already correct in the first pass. |
| Stale iframe/template content | None — every `openFromTrigger()` call (including retargeting to a second template while already open) always calls `loadCurrentUrl()`, and `closeDialog()` additionally resets `frame.src = 'about:blank'`. |
| Industry hiding/filtering | None — `storefront_template_gallery()`'s context/query is untouched; `test_gallery_lists_every_registered_ready_template` proves all 50 still render. |
| Accidental W5D scope creep | None — no page-type switcher, no convenience Apply-from-dialog button, no capture-pipeline change were added; all explicitly out of scope per the plan's non-goals. |

## Outcome (round 1)

**CRITICAL: 0. IMPORTANT: 0.** (All 4 findings from the first pass were
fixed before this document's final state; the re-review found nothing
further.)

---

# Round 2 — Independent Architect repair

## What the round-1 automated pass missed

The Architect's own direct source review found two real gaps in
`storefront_template_live_preview` that round 1's automated `code-review`
pass (high effort) did **not** catch: no `@require_GET` (a POST was
silently accepted), and Demo mode's candidate resolution used the
write-capable `get_or_create_draft` instead of the non-creating
`get_existing_draft` Merchant mode already used. This is recorded
honestly rather than glossed over — round 1's "CRITICAL 0 / IMPORTANT 0"
verdict was correct for the files it was scoped to at the time, but the
Preview route's actual method/persistence contract had not been checked
against its own documented claims.

## Fixes (see `preview_authority_chain.md` / `non_mutation_proof.md` for the full account)

- `@require_GET` added to `storefront_template_live_preview`.
- Demo mode's candidate resolution changed to `get_existing_draft`,
  mirroring Merchant mode exactly.
- `template_gallery_preview.js` gained an Escape handler attached to
  each newly-loaded iframe document (`load` event), closing the gap
  where Escape did nothing once focus moved inside the same-origin
  preview iframe.

## Fresh independent code-review pass over the repair diff itself

Run at effort level `high` over `views.py`, `template_gallery_preview.js`,
both touched test files, and the browser QA script. **3 findings:**

| # | Finding | Disposition |
|---|---|---|
| 1 | Demo mode's new no-bootstrap check requires an active Draft on `rasti-mode-demo`, but no production code path created one — `apply_golden_reference_storefront` publishes (`layout.draft_version = None`) and nothing re-creates a Draft afterward, so a freshly-seeded environment's Demo Preview would 404 indefinitely, and the 404 message's own suggested remedy (re-running that command) would not fix it. | **Fixed** — `apply_golden_reference_storefront` (the management command) now calls `layout_service.get_or_create_draft(store)` as an explicit final step after publishing, exactly mirroring how a merchant's own Store always has a fresh Draft the moment they open their Gallery. Idempotent (get-or-create), matching the command's own existing idempotency contract. See `apps/stores/management/commands/apply_golden_reference_storefront.py`. |
| 2 | The new Escape-inside-iframe fix does not extend the existing `Tab`/`Shift+Tab` focus-trap block to intercept Tab keydowns fired inside the iframe's own document (the same root cause as the Escape gap, for a different key). | **Considered, not applied — out of the authorized repair scope.** The Architect's directive (§7) asked specifically for Escape-from-inside-the-iframe; extending the Tab-trap into the iframe is a materially larger, unrequested change, and §9 explicitly forbids widening this repair into a new architecture. Topology check: in this dialog's actual DOM order (Close → data-source buttons → device buttons → iframe → "open in new tab" link), both directions of iframe-boundary Tab traversal land on an element STILL INSIDE the dialog (the new-tab link forward, the "mobile" device button backward) — from either landing point, the existing parent-document Tab handler correctly re-establishes the wrap on the next Tab press. So while the code-level observation is correct (the trap block's code path is never entered for an iframe-internal Tab keydown), the practical risk of focus actually escaping the dialog is mitigated by this specific markup's ordering, not by the trap logic itself. Documented here rather than silently dropped. |
| 3 | Merchant and Demo branches in `storefront_template_live_preview` now contain near-duplicate "resolve existing Draft or 404" blocks. | **Not applied — optional style nit, not a correctness issue, not one of the Architect's named findings.** Left as two small, independently-readable blocks with their own distinct Persian error messages rather than introducing a new shared helper for a 2-call-site pattern, consistent with keeping this repair's diff minimal and scoped to exactly what was asked. |

## Outcome (round 2)

**CRITICAL: 0. IMPORTANT: 0.** Finding #1 (the only one with a real
failure scenario) is fixed. Findings #2 and #3 are documented,
deliberate scope decisions, not overlooked defects.
