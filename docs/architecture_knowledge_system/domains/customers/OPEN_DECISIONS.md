# customers — Open Decisions

```
domain_id: D3
code_baseline: 5883a140
```

Full detail: [`../../canonical/ARCHITECTURAL_DECISION_REGISTER.md`](../../canonical/ARCHITECTURAL_DECISION_REGISTER.md).

## No DR-1…DR-8 item originates in customers
customers has no open architectural decision from the DR register.

## Context / relevant notes
- **Readiness POOR** (documentation): before this pack there was no consolidated CRM/segment doc.
  This is a documentation gap, not an open architecture decision.
- **CRM services live in `dashboard`** (customer_crm_service / segment_service) — a cross-domain
  write pattern. Not a DR, but relevant if a future decision proposes a customers-owned CRM service.
- **Customer is global (ADR-6/50)** — making it store-scoped would be a significant design change,
  not currently on the register.

No option is selected.
