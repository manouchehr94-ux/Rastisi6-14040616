# subscriptions — Boundaries

```
domain_id: D7
code_baseline: 5883a140
known_risks: M7
```

## Owns
`StoreSubscription` + its canonical state machine; `Plan`/`PlanVersion`; `EntitlementDefinition`/
`PlanEntitlement`; `SubscriptionEvent`; `UsageRecord`; entitlement resolution + enforcement.

## Does NOT own
- **Invoicing / payment / dunning / refunds** — `billing`. billing *drives* subscription transitions;
  subscriptions does not invoice.
- **Store identity** — `stores`.
- **Money movement** — no money moves here (ADR-72: plan change alters entitlements; payment is billing).

## Cross-domain relationships
- **In (drives subscription transitions, funneled — M7):** `billing` confirmation/dunning/renewal/
  cancellation; `plan_change_service` override.
- **Out:** none direct (subscription_service is called; it doesn't call other domains for state).
- **Read by:** `stores.publication_service` (entitlement/access), `dashboard` (subscription banner).

## Fail-open note (M8)
`entitlement_service` fails open (no subscription → treated as access-granted), so a store without a
subscription remains usable — which propagates to store-visibility failing open.
