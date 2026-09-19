# W5C — Accessibility Review

Contract R. Static markup is proven by
`GalleryDialogAccessibilityMarkupTests`
(`test_phase5_w5c_ready_template_preview_ux.py`); dynamic focus/keyboard
behavior is proven live by browser QA (`browser_qa.md`).

## Existing pattern followed

The dialog reuses the SAME behavioral contract this codebase already
establishes for admin-page dialogs — the site-wide command palette
(`#adminV2CommandPalette` / `apps/dashboard/static/js/admin_v2.js`,
loaded on every admin page including the Gallery via `base_admin.html`):
an open/closed class toggle plus `aria-hidden`, Escape closes, backdrop
click closes, focus moves into the dialog on open, and focus is restored
to the triggering element on close. `resource_picker.html` (R4's own
`role="dialog" aria-modal="true"` overlay) confirms the same
overlay-wraps-dialog structure is already an established idiom, not a
new pattern invented for W5C.

## Static markup contract (Django-test-verified)

- `role="dialog"` — present.
- `aria-modal="true"` — present.
- `aria-labelledby="tplPreviewTitle"` (pointing at the real title
  element) — present.
- An explicit, labeled Close control (`data-tpl-preview-close`,
  `aria-label="بستنِ پیش‌نمایش"`) — present.
- Device buttons expose `aria-pressed` in their initial server-rendered
  state (`desktop` starts `true`, `tablet`/`mobile` start `false`) —
  present, matching R4's own device-switcher convention.
- Data-source buttons expose `aria-pressed` similarly.

## Dynamic behavior (JS, browser-QA-verified)

- **Opening**: focus moves to the Close button (the dialog's first
  logical interactive control), mirroring the command palette's own
  "focus the primary interactive element" pattern.
- **Escape**: closes from anywhere while the dialog is open (a
  document-level `keydown` listener gated on `isOpen()`, same idiom as
  the command palette).
- **Explicit Close button**: closes and restores focus to whichever
  trigger opened the dialog (`state.lastTrigger`).
- **Backdrop click**: closes (click directly on `[data-tpl-preview-root]`,
  not inside the dialog card).
- **Focus restore**: the exact trigger element that was clicked/activated
  is remembered and re-focused on close — not just "the first trigger on
  the page" or "the top of the Gallery."
- **Focus trap**: a `Tab`/`Shift+Tab` handler (added during independent
  code review — see `code_review.md` finding #4) keeps focus cycling only
  among the dialog's own focusable elements (Close button, data-source
  buttons, device buttons, the iframe, the "open in new tab" link) while
  open, so the merchant is never tabbed onto a Gallery card hidden behind
  the opaque backdrop.

### Known, documented limitation: focus that moves INSIDE the iframe

Keyboard `Tab` events fired while focus is inside the preview `<iframe>`'s
own (same-origin) document do not bubble to the top document's listeners
— this is a general property of iframes, not something `template_gallery_
preview.js` can intercept from the parent frame without also reaching
into the iframe's document and installing a second listener there. In
practice the live-preview page's own content is a normal storefront page
(links, buttons) whose own tab order is bounded and finite, and tabbing
past its last element returns focus to the browser's native document tab
order at the point the iframe sits in — which, in this dialog, is
immediately followed by the "بازکردن در تبِ جدید" link, still inside the
dialog. This is a known nuance of accessible modals that embed iframes
generally (not specific to this codebase or this phase) and is
consistent with the directive's own framing ("no keyboard trap outside a
**real modal contract**" — the trap covers the dialog's own top-level
controls, which is what contract R requires); it is documented here
rather than silently left unmentioned.

## Keyboard reachability

Every trigger (screenshot link, both "مشاهده..." links) is a real
`<a href>` — reachable and activatable by keyboard (`Enter`) exactly like
any other link, with no custom `tabindex`/role needed, since W5C
deliberately kept them as real anchors (see the implementation plan's "no
second QA/interaction framework" and "graceful degradation" requirements)
rather than converting them to `<button>` or `<div>` elements that would
need manual keyboard-activation wiring.
