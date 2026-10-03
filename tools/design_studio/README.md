# Design Studio reference CSS

`apps/storefront_builder/static/storefront_builder/r4_studio.css` starts with the
workspace stylesheet of the approved visual reference
`RastiSi_Design_Studio.html` (SHA256
`702f2c4a09faa8f72ac79de59803d1c5e44d1aea1c08a7cf650e795b6bcf5826`), mechanically
scoped under the `.rs-studio` root so it never styles the dashboard, the public
storefront or any other editor.

Regenerate the scoped layer (first `<style>` block of the reference) with:

    python tools/design_studio/scope_reference_css.py reference_workspace.css > scoped.css

Every selector gets exactly one extra `.rs-studio` class, so the reference's
successive overrides resolve to the same final computed values. `:root`/`html`/
`body` map to the Studio root; `#app`, `#modal-root`, `#toast` and
`#storefront-preview` map to `.rs-app`, `.rs-modal-root`, `.rs-toast` and
`#r4PreviewFrame`; keyframes are prefixed `rs-`.

The hand-written "R4 integration layer" at the end of `r4_studio.css` only adapts
real R4 components (inspector fields, container settings, repeaters, media
manager, gallery thumbnails) to the reference vocabulary.
