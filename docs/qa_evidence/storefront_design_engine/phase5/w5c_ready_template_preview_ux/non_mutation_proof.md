# W5C — Non-Mutation Proof

**Repaired by the Independent Architect's review — see the "Round 2"
section near the end of this document for the corrected, authoritative
account.** The original text below is preserved for the historical
record, but its claim that the route was "already, before W5C, GET-only"
was **false** — see Round 2.

Opening the Preview dialog, retargeting it to a different Ready Template,
switching Desktop/Tablet/Mobile, and switching Merchant/Demo data must
never mutate Draft or Published state. This is contract H/I/J/K.

## Why device switching needs no Django-level proof of its own

Device switching (`setDevice()` in `template_gallery_preview.js`) is pure
client-side CSS: it only ever sets the SAME iframe's `style.width`/
`style.height`/`style.transform` and toggles button `aria-pressed`
attributes — it makes zero network requests and touches no server route
at all. There is nothing for a Django test to observe here beyond "no
request was made," which is definitionally true by inspection of the
function (no `fetch`/`XMLHttpRequest`/form submission anywhere near it).

## What DOES reach the server, and is proven non-mutating

Opening the dialog, retargeting to a different template, and switching
data source all resolve to exactly one thing at the Django level: a GET
request to `storefront_template_live_preview` (Demo or `?data=merchant`).
`GalleryPreviewNonMutationTests`
(`test_phase5_w5c_ready_template_preview_ux.py`) proves each of these
directly, using the same full-lifecycle snapshot shape as the existing
Task-3 non-mutation tests (`draft PK`, `edit_revision`,
`appearance_config`, `header_config`, `footer_config`,
`template_provenance`, the full ordered section list, container count,
edit-history-entry count, and the layout's `published_version_id`):

| Test | What it proves |
|---|---|
| `test_opening_gallery_is_non_mutating` | Loading the Gallery page itself (which already, pre-W5C, calls `get_or_create_draft`) is non-mutating. |
| `test_opening_demo_preview_is_non_mutating` | Opening a Preview trigger defaulted to Demo mode (one GET to the bare canonical URL) is non-mutating. |
| `test_opening_merchant_preview_is_non_mutating` | Opening a Preview trigger defaulted to Merchant mode (one GET with `?data=merchant`) is non-mutating. |
| `test_switching_data_source_back_and_forth_is_non_mutating` | Four round-trips (Merchant→Demo→Merchant→Demo) for the SAME template — simulating a merchant repeatedly toggling the data-source control — produce zero net (or intermediate) mutation. |
| `test_retargeting_to_a_second_template_is_non_mutating` | Opening Template A then Template B in the same dialog session (mirrors browser QA step 31) is non-mutating. |
| `test_previewing_template_x_does_not_change_current_template_provenance` | With a REAL applied template already in place (`dense_marketplace`, via `preset_service.apply_preset`), previewing a DIFFERENT template (`premium_leather`) in both data modes leaves `template_provenance` pointing at `dense_marketplace` — contract K, proven end-to-end. |

All six pass. No test needed to be weakened or special-cased to make this
true — `storefront_template_live_preview` was already, before W5C,
GET-only and backed entirely by `preset_service.resolve_preset_candidate`,
which has never persisted anything (confirmed by direct source read, see
`preview_authority_chain.md`). W5C's one production-logic change
(`@xframe_options_sameorigin`) does not touch any read/write path — it
only changes an HTTP response header.

## Repeated-load stress (§19's "before/after every interaction" spirit)

The data-source round-trip test above issues 4 separate GET requests
against the SAME Draft before taking its "after" snapshot — proving not
just "one preview load is safe" but that repeated opens/switches (as a
merchant realistically would while comparing options) never accumulate
any mutation, revision advance, or extra history entry.

---

# Round 2 — Independent Architect repair (AUTHORITATIVE)

The Independent Architect's source review of PR #15 found the claim
above — "the route was already, before W5C, GET-only" — **was false**,
and found a second, more serious gap alongside it:

1. **No `@require_GET`.** `storefront_template_live_preview` had no
   method restriction at all; a bare POST was silently accepted (200) by
   whatever branch matched, rather than getting a controlled 405. The
   original evidence's "GET-only" framing was an unverified assumption,
   not a checked fact.
2. **Demo mode could bootstrap a Draft.** Demo mode resolved its
   candidate via `layout_service.get_or_create_draft(preview_store)` —
   name notwithstanding, this is a **write path**: if the canonical Demo
   Store had no active Draft, a plain GET request would silently create
   one. Merchant mode already correctly used the non-creating
   `get_existing_draft`; Demo mode did not, which is precisely the kind
   of asymmetry that should never survive a "both modes are read-only"
   claim without being checked in both directions.

**Do not pretend the first report was correct — it was not.** The
non-mutation contract was true for Merchant mode and false for Demo mode
until this repair.

## The repaired, truthful contract

- `storefront_template_live_preview` is now `@require_GET` — a POST
  returns a controlled 405 (Django's built-in `HttpResponseNotAllowed`),
  never accepted, never mutates anything.
- Demo mode now resolves its candidate via the SAME `get_existing_draft`
  Merchant mode uses. If the canonical Demo Store has no active Draft,
  the request fails closed with 404, exactly like Merchant mode already
  did for a Store with no Draft — never silently bootstrapping one.
- Both data modes now share the identical "read an existing Draft or
  fail closed" contract. Preview creates **zero persistence** in either
  mode, proven directly against the database.

## New tests (all in `test_phase5_w5c_ready_template_preview_ux.py`
unless noted)

| Test | What it proves |
|---|---|
| `PreviewMethodContractTests.test_merchant_preview_post_is_405` | A POST to Merchant Preview is rejected with 405; the Draft snapshot is unchanged before/after. |
| `PreviewMethodContractTests.test_demo_preview_post_is_405` | A POST to Demo Preview is rejected with 405. |
| `DemoPreviewNoBootstrapTests.test_demo_preview_without_a_draft_404s_and_creates_nothing` | A canonical Demo Store created WITHOUT any Draft: GET Preview → 404, and `StorefrontLayout`/`StorefrontLayoutVersion`/history-entry counts for that Store are proven to be `0` both before and after — no Draft, Layout, or history row was created by the GET. **This is the test that reproduces the original bug: it fails (200, with a silently-created Draft) against the pre-repair source, and passes only after the fix.** |
| `SeededDemoPreviewNonMutationTests.test_seeded_demo_preview_does_not_mutate_the_demo_draft` | With a REAL seeded Demo Draft, the same full-lifecycle snapshot used for Merchant mode (PK, `edit_revision`, `appearance_config`, `header_config`, `footer_config`, `template_provenance`, ordered section list, container count, history count, `published_version_id`) is byte-identical before/after a Demo Preview GET. |
| `SeededDemoPreviewNonMutationTests.test_repeated_seeded_demo_preview_loads_do_not_accumulate_mutation` | Three repeated Demo Preview loads still produce zero net/intermediate mutation. |
| `MerchantPreviewNoBootstrapRegressionTests.test_merchant_preview_without_a_draft_404s_and_creates_nothing` | Merchant mode's existing no-bootstrap behavior (already correct pre-repair) is reconfirmed with the same DB-level proof style used for the Demo-mode fix, in this module. The fuller original version of this contract remains in `test_task2_live_demo_template_preview.py`/`test_task3_merchant_template_preview.py`, unmodified except for one fixture fix (below). |

## Genuine RED verified before the fix

The production fix was temporarily reverted via `git stash` (isolated to
`views.py` only, no test file touched), the new test module was run, and
exactly 3 tests failed for the expected reason — `test_demo_preview_post_
is_405`, `test_merchant_preview_post_is_405` (both 200 instead of 405),
and `test_demo_preview_without_a_draft_404s_and_creates_nothing` (200
with a Draft silently created, instead of 404 with none created). The
stash was then restored and all tests confirmed green. Raw output:
`tdd_red.txt`'s repair-round section is superseded by this document; the
raw RED/GREEN logs for the repair itself are not separately committed
(the targeted stash-based verification above is the durable record).

## A second real regression found by the repair's own independent code review

Fixing Demo mode's candidate resolution surfaced a genuine regression in
the **pre-existing, unmodified** `test_task2_live_demo_template_preview.py`
suite: its shared `LiveDemoTemplatePreviewTestCase.setUpTestData` only
ran `apply_golden_reference_storefront` — which both applies AND
**publishes** the Demo Store's Draft (`layout_service.publish()` sets
`layout.draft_version = None`) — with no subsequent Draft re-creation.
Several of that module's tests (which never called
`svc.get_or_create_draft(self.demo_store)` themselves, unlike others in
the same file) would 404 once Demo mode correctly stopped silently
bootstrapping a replacement. Confirmed by a full run BEFORE the fixture
fix: **7 failures**. Fixed the same way this phase's own new fixture
already was: `setUpTestData` now explicitly creates the real, expected
post-publish Draft. Confirmed AFTER the fix: **20/20 PASS**
(`focused_tests.txt`'s repair-round section).

## Conclusion (Round 2)

The truthful, repaired contract: `storefront_template_live_preview` is
GET-only (405 on any other method) and creates zero persistence in
either data mode — Demo and Merchant now share the exact same
"read-existing-or-fail-closed" candidate-resolution path.
