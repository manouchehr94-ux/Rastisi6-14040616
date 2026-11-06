# Password visibility (UI-PASSWORD-01) — 2026-11-06

Branch `ux/platform-merchant-remediation-20261106`. Local only.

## Product rule implemented
Every password input has an eye button inside its **right** side; the characters are typed from the **left** (`direction:ltr; text-align:left`); labels and the form stay RTL.
Implemented once, in the shared component (`apps/core/static/core/password_toggle.{js,css}`), independent of page direction.

## Audit (real Chromium, synthetic data, 15 pages x 2 widths 1440/390)
| | visible inputs | problems |
|---|---|---|
| Before (Checkout `8ad4b687`) | 46-48 | **100** |
| After | **58** | **0** (and 0 of 102 inputs — visible or hidden — left unwrapped) |

Findings before the fix:
* **Public site v2 (`/login/`, `/login/password/`, `/login-email/`, and by redirect the merchant-admin login) had no eye at all.** `auth-forms.js` removed its own toggle in favour
  of the shared component, but `public_v2/base.html` never loaded it. A second guard test could not see this: it matched `extends "…auth_base.html"` against the suffix `base.html`.
* Platform Admin: eye on the **left** for RTL inputs (login, SMS providers), 30px target, and `.pa input.pa-ltr{text-align:right}` right-aligned the typed text (gateway credentials).
* Storefront login modal: eye on the left for an RTL-direction input.

Fixes: `password_toggle.js` forces `dir="ltr"` and marks the input; the CSS pins `direction/text-align/padding-right` (beating page overrides) and positions the eye with
`right:4px`; `public_v2/base.html` loads the component; Platform Admin target 30px → 32px; cache-busters bumped on all six bases.

## Accessibility / behaviour (unchanged and re-verified by the browser tests)
`aria-label` ("نمایش رمز" / "پنهان‌کردن رمز"), `aria-pressed`, `aria-controls`, keyboard operable, visible focus ring, hidden by default, hidden again on submit/reset/bfcache,
name/value/autocomplete untouched (password managers keep working), late-inserted fields (HTMX/Alpine) enhanced, one button per field, opt-out only via `data-pw-toggle="off"` (none used).
Targets: 44px (46px ≤480px); Platform Admin's dense 37px controls use 32px (≥ WCAG 2.2 AA 24px; **not** the 44px AAA recommendation).

## Tests
`apps/core/tests/test_password_toggle.py` (12; 4 need `SFB_BROWSER_TESTS=1`): host wiring now includes `public_v2/base.html`; the "every template with a password input" test resolves the
whole `extends` chain by exact file; geometry asserts the physical right + ltr/left in RTL and LTR pages at 1440/390. Verified to fail when the v2 base wiring is reverted.

## Not verified in a browser (needs OTP state)
`/register/`, `/register-email/`, `/reset-password/new/`, `/signup/complete/` render their password fields only after an OTP step. They extend the same v2 base (now wired and
guarded) and use the same wrapper, but their exact geometry is **NEEDS_MANUAL_VALIDATION**.
