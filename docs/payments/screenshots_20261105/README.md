# Platform Admin screenshots (2026-11-05)

Captured with Chromium against a **scratch PostgreSQL database seeded with synthetic data** (no real credentials, cards or money). Each page was loaded at 1440 px and 390 px: HTTP 200, **0 px horizontal overflow, no JavaScript errors**.

| File prefix | Page |
|---|---|
| `gateways-v2-*` | Platform Admin → Payment Gateways: per-method status, gate lists, purchase types, platform card-to-card form; no COD row |
| `manual-claims-queue-*` | Card-to-card review queue |
| `manual-claim-review-*` | Claim review: server-side expected amount, receipt link, bank-reference + exact-amount form, reject form, append-only history |
| `reconciliation-v2-*` | Reconciliation: verified-but-unsettled attempts, pending/overdue card claims |
| `owner-card-claim-*` | Store owner: destination card, exact amount, claim form |
| `owner-invoice-methods-*` | Store owner invoice page with the card-to-card method |

`gateways-desktop-1440.png` / `gateways-mobile-390.png` are the earlier (pre-gates) captures kept for comparison.
