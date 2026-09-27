// Final-QA correction — the ONE canonical Alpine `x-data="destinationPicker(...)"`
// factory for the R4/standalone media add/edit form
// (partials/section_media_form_body.html), shared by its two real page
// contexts:
//
//   * the R4 Design Studio (r4/editor.html), where this form is loaded
//     inline into the Inspector via `innerHTML`/htmx (a <script> embedded
//     in that swapped fragment never executes, per the DOM spec — this
//     file is a normal <script src>, executed by the browser's own parser
//     during the R4 Studio page's initial load, well before any such swap);
//   * the standalone legacy-style full-page media add/edit screen
//     (partials/section_media_form.html), a genuine full page load where
//     this same file is loaded the same way.
//
// This does NOT touch or replace the pre-existing, separate R3/legacy full
// editor's own inline `destinationPicker` (dashboard/storefront_builder/
// editor.html) — that page is a different, mutually-exclusive context
// (rendered only when the R4 editor is disabled) and is out of scope here.
window.destinationPicker = window.destinationPicker || function (initialType, initialId, initialName) {
  return {
    type: initialType || 'none',
    productId: initialType === 'product' ? initialId : null,
    productName: initialType === 'product' ? initialName : '',
  };
};
