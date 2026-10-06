# Owner login QA evidence (`audit/owner-login-v1`)

Real Chromium, real Django dev server (SQLite, console e-mail, OTP codes read from a
local test sink — never logged by the app), Turnstile disabled except where stated.
Viewports: desktop 1440×900, tablet 768×1024, mobile 390×844 (DPR 2, touch).

| File | Viewport | Route / state | What was verified |
|---|---|---|---|
| `login-password-1440.png` | 1440 | `/login/` password tab, clean | Form + story side by side; selected tab obvious; password toggle (added by JS only) |
| `login-password-768.png` | 768 | `/login/` clean | Single column, no horizontal overflow. The **header** still wraps its links at this width (pre-existing, see "Known issues") |
| `login-password-390.png` | 390 | `/login/` clean | Form first, primary action above the fold, tabs side by side |
| `login-invalid-390.png` | 390 | `POST /login/password/` wrong password | One generic alert; both fields `aria-invalid` + `aria-describedby="id_form_error"`; focus moved to the identifier; password not echoed |
| `login-rate-limited-390.png` | 390 | 11th attempt for one identifier | Per-identifier throttle message (applies equally to unknown identifiers) |
| `login-otp-1440.png`, `login-otp-390.png` | 1440 / 390 | `/login/?mode=otp` | Truthful copy: existing owner logs in; a new number is asked for a name after verification |
| `verify-wrong-code-390.png` | 390 | `/verify/` wrong code | Field-level Persian error, countdown, resend cooldown, focus on the code field |
| `verify-resend-390.png` | 390 | `/verify/` after resend | Success flash (`role=status`), new code supersedes the old |
| `login-success-app-390.png` | 390 | OTP login of an existing owner → `/app/` | Direct login, no new Store |
| `signup-complete-handoff-390.png` | 390 | new phone → verified → `/signup/complete/` | Regression of the hardened hand-off: **no User / OwnerProfile existed before the name step** (checked in the DB); a one-character name is rejected beside the field; a valid name → onboarding |
| `reset-request-1440.png`, `reset-request-390.png` | 1440 / 390 | `/reset-password/` | Same design system as login (previously a different button/container class set) |
| `reset-request-invalid-email-390.png` | 390 | invalid e-mail | Error is now visible beside the field (it used to be silently dropped). *Captured before the message was shortened to avoid a bidi-scrambled inline example.* |
| `reset-request-sent-390.png` | 390 | after POST | Same generic confirmation for known and unknown e-mails |
| `reset-confirm-errors-390.png` | 390 | valid link, mismatched passwords | Requirement list comes from `AUTH_PASSWORD_VALIDATORS`; mismatch error on the confirmation field; `autocomplete="new-password"` |
| `reset-invalid-token-390.png` | 390 | link opened a second time | HTTP 400 "invalid or expired" page |
| `reset-success-login-390.png` | 390 | after a successful reset | Inline `role=status` message (not the bottom toast), then password login with the new password works |
| `admin-return-handoff-1440.png` | 1440 | `store-…rastisi.localhost/admin-portal/` → central login → back | Cross-host hand-off: signed `admin_return`, ACTIVE membership check, one-time ticket, landing on the admin host |

Also exercised in the browser (no screenshot): logout is POST-only (GET → 405) and ends the
session; `GET /login/password/` redirects to `/login/` instead of a bare 405; JS tab switching
updates `?mode=` and `aria-current`; weak passwords show Persian policy messages and focus the
first invalid field.

## Found by browser QA (not by the unit tests)

* `Referrer-Policy: no-referrer` on the reset-confirm page made Chromium POST with
  `Origin: null`, which Django's CSRF origin check rejects (403) — the form was unusable.
  Fixed with `same-origin`; the regression test pins the header value and explains why.

## Not captured

* Turnstile failure and provider failure states are covered by tests
  (`test_owner_login_audit.LoginTurnstileTests`, `OtpLoginThroughViewTests`) but were not
  screenshotted (the Turnstile widget needs Cloudflare network access).

## Known issues (not changed here)

* Public header links wrap at ~768px (the nav only collapses ≤720px). A scoped fix (collapse to
  the hamburger ≤900px) was tried and reverted: the mobile menu panel's styles only exist inside
  the ≤720px media query, so it rendered unstyled over the form at 768px. Needs a proper header
  pass, not a login-page tweak.
