# W5C — Non-Mutation Proof

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
