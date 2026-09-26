# customers — Security

```
domain_id: D3
code_baseline: 5883a140
```

## Auth (VERIFIED)
- Customer auth = phone + password / OTP (`auth_service`, username == phone). Guest checkout
  auto-creates accounts with random passwords. Enumeration-safe generic errors.
- OTP flows via customers routes (otp/request, otp/login, otp/reset) + `sms.otp_service`.

## Shared identity (ADR-102)
A customer and an owner can be the **same** `auth.User` (username == phone). A password/OTP change
affects both roles. Treat customer auth changes as potentially affecting owner login.

## Tenancy
- `Customer` is global (intentionally not store-scoped). Per-Store data is `CustomerProfile`
  (`uniq_customerprofile_per_store`), tags/notes/segments (store-scoped). CRM admin views (in
  dashboard) are Store-scoped and permission-gated.

## Cart merge fence
`merge_guest_cart` uses `select_for_update` (CAT-002 membership fence) to merge the guest cart into
the user cart safely.

## No signals
Profile stats refresh explicitly (ADR-50) — no signal-driven side effects.
