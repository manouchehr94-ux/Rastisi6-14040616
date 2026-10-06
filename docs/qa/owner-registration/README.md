# Owner registration audit (`audit/owner-registration-v1`)

Evidence and notes for the registration / signup hardening pass. Screenshots were
captured in Chromium against a local dev server (PostgreSQL, console OTP enabled
with `RASTISI_OWNER_SMS_ALLOW_CONSOLE_OTP=true` — never set this in production).

## Flow (as implemented)

```
/register/ (name + phone, Turnstile)
  → OwnerRegistrationRequestForm: normalized name (required), canonical phone
  → owner_otp_service.request_otp (IP + phone limits, hashed code, SMS)
  → server session: phone, purpose=register, full_name, remember_me
/verify/ (code only; phone/name come from the session)
  → owner_otp_service.check_otp  (atomic: reserve attempt → conditional consume)
  → owner_auth_service.resolve_owner_identity_by_phone
       → OwnerIdentityResult(user, user_created, owner_created)
  → django login (session key cycled)
  → owner_created ? provisioning_service.provision_initial_trial_store : normal redirect
  → /app/stores/<id>/onboarding/ → identity → industry → branding → review
```

`/verify/resend/` (POST, session-bound) re-issues a code for the in-flight request.

## Enforced policy

| Flag | Enforced? | Where |
| --- | --- | --- |
| `new_store_registration_enabled` | **Yes** | `/register/` (GET shows notice, POST issues no OTP), `/verify/` + `/verify/resend/` (no new Owner may be created / registration OTP not re-sent), and `provisioning_service.provision_trial_store` (service layer; also blocks an existing owner's *additional* store). Read straight from the DB, never from the 5-minute config cache. Existing owners can still log in and use existing stores. |
| `maintenance_mode_enabled` | **No** | Stored and editable only; nothing reads it. Its help text promises more than is implemented. Needs a product decision before enforcement. |

## Screenshots

| File | State |
| --- | --- |
| `before-register-*` | Original page (form below the story on mobile, ≤11px text) |
| `01`–`03` | Clean register: 1440 / 390 / 768 |
| `04`, `18` | Validation errors (mobile / desktop) |
| `05` | Turnstile failure |
| `06` | OTP delivery failure |
| `07` | OTP rate limit |
| `08`, `09` | Verify page (registration), mobile / desktop |
| `10` | Wrong code |
| `11` | Expired code |
| `12` | Resend confirmation |
| `13`, `14` | Landing in onboarding after signup |
| `15`, `19` | Login (password / OTP tab with the "OTP can create an account" note) |
| `16`, `17` | Registration closed |
