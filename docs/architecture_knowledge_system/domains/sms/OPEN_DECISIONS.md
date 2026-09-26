# sms — Open Decisions

```
domain_id: D12
code_baseline: 5883a140
```

Full detail: [`../../canonical/ARCHITECTURAL_DECISION_REGISTER.md`](../../canonical/ARCHITECTURAL_DECISION_REGISTER.md).

## No DR-1…DR-8 item originates in sms
sms has no open architectural decision from the DR register.

## Relevant notes (not DRs)
- **`ShopSettings` legacy SMS credential fields are POTENTIALLY_DEAD** (D4 register) — ignored by
  `sms_service` except the `SMSRASTI` backend selection. Real creds come from
  `portal.PlatformConfiguration`. Not a DR, but relevant to any ShopSettings cleanup (touches DR-3's
  neighborhood).
- **Wide send surface** — several public send functions; documented, all funnel through `_dispatch`.
- Readiness POOR is a documentation gap (device-gateway/credit model previously undocumented), now
  addressed by this pack — not an open decision.

No option is selected.
