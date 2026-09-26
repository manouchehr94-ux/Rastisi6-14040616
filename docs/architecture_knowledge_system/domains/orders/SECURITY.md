# orders — Security

```
domain_id: D6
code_baseline: 5883a140
```

## Trust boundaries (VERIFIED)
- **Browser return is never payment proof.** The gateway path confirms via server-to-server
  `adapter.verify_payment`; the simulation path is production-disabled.
- **`gateway_callback` is public** (no auth — a gateway calls it) but trusts only the verify call,
  never the request body. Idempotent on attempt `is_final`.
- **`payment_callback` (simulation)** takes a **client-controlled** `status` path segment and is
  therefore `Http404` in production via `PAYMENTS_SIMULATION_ENABLED` (defaults to `DEBUG`).
- **Amount/currency** validated against the server-side order/attempt snapshot.

## Credential handling (VERIFIED)
- Gateway credentials stored in `PaymentGatewayConfig.encrypted_credentials`, encrypted with
  Fernet via `apps/orders/encryption.py` (key `PAYMENT_CREDENTIAL_KEY`, independent of Django
  `SECRET_KEY`). Missing key in production → fail-closed startup. Credentials never shown in full.

## Tenancy (VERIFIED)
- Orders are Store-scoped (`Order.store`, PROTECT FKs); `Order.clean()` enforces
  `vendor.store == order.store`. Dashboard order views are scoped to `request.store`.

## Payment-integrity risk surface (⚠️ H1 / DR-1)
- `Order.payment_status` has three writers and no transition guard. A change that introduces a
  fourth writer, or that assumes a single guarded transition, is a correctness/financial-integrity
  risk. Any security review of payment flows must account for all three writers.

## PII / SMS
- Payment/order SMS fire on `transaction.on_commit` (never on a rolled-back order). SMS content is
  template-rendered; OTP/secret content is not logged (see `sms` domain).
