# Domain: content (D10) — Content & Navigation

```
domain_id: D10
app: apps/content
status: CANONICAL
readiness: POOR
code_baseline: 5883a140
last_verified_against_code: 5883a140
source_phases: Phase 1 / Phase 2 / Phase 4
open_decisions: DR-2
known_risks: H2, M2, M11, O2
```

> **Critical, do-not-overlook fact (finding H2):** `apps/content` has **NO write service**. Its
> models are Store-owned, but **all create/update/delete happens in `apps/dashboard/views.py`**
> (direct `.save()`/`.full_clean()`/`.delete()`). This pack does **not** pretend a canonical content
> write service exists — because it does not. The write-boundary question is **OPEN as DR-2**.

## Pack contents
[BOUNDARIES](BOUNDARIES.md) · [DATA_MODEL](DATA_MODEL.md) · [MUTATION_AUTHORITY](MUTATION_AUTHORITY.md) ·
[SERVICES](SERVICES.md) · [ENTRY_POINTS](ENTRY_POINTS.md) · [DEPENDENCIES](DEPENDENCIES.md) ·
[STATE_MACHINES](STATE_MACHINES.md) · [INVARIANTS](INVARIANTS.md) · [SECURITY](SECURITY.md) ·
[TESTING](TESTING.md) · [CHANGE_GUIDE](CHANGE_GUIDE.md) · [CODE_MAP](CODE_MAP.md) ·
[HISTORICAL_CONTEXT](HISTORICAL_CONTEXT.md) · [OPEN_DECISIONS](OPEN_DECISIONS.md)

**Not-applicable docs** (recorded here instead of empty files): `API_AND_EVENTS.md` (no external
API; no signals — the only "event" is the MED-001 no-op cleanup callback),
`TRANSACTIONS_AND_CONCURRENCY.md` (no content service owns a transaction boundary — writes happen in
dashboard views; see [MUTATION_AUTHORITY](MUTATION_AUTHORITY.md) and DR-2),
`ARCHITECTURE.md`/`FLOWS.md`/`TROUBLESHOOTING.md` (folded into this README + CHANGE_GUIDE given the
domain's small, view-driven nature).

## Orientation (the 18 questions, condensed)
1. **Owns:** CMS pages, navigation menus, footer settings/media, section-scoped placements
   (hero/banner/story), social links, newsletter, media assets. (data only)
2. **Does NOT own:** its own write path (dashboard does); the storefront layout sections it FKs into
   (`storefront_builder`); the render shell (`storefront_builder.render_service`).
3. **Models:** 12 models + `DestinationMixin`. See [DATA_MODEL](DATA_MODEL.md).
4. **Canonical services:** **none for writes.** `content/services.py` is read/resolve + newsletter +
   MED-001 no-op cleanup only. See [SERVICES](SERVICES.md).
5. **Non-domain writers:** `dashboard.views` (primary — H2); `storefront_builder` (placement media clone).
6. **Who calls it:** storefront render (reads); dashboard (writes).
7. **What it calls:** `catalog` (destination resolution), `storefront_builder` (FK).
8. **Entry points:** public `page_detail` + `newsletter_subscribe`; all CRUD via dashboard routes.
9. **State machines:** `ContentPage.status` (draft/published). See [STATE_MACHINES](STATE_MACHINES.md).
10–13. Invariants / (no) transactions / security → linked docs.
14. **Tests:** mostly via dashboard content-view tests. See [TESTING](TESTING.md).
15. **Smells:** H2 (no write service), M2 (footer ×3), M11 (dual media), O2 (MED-001 no-ops).
16. **Open DR:** **DR-2** (content write boundary).
17. **Historical:** SAAS_MIGRATION_PLAN PR-8 (ownership modeled; service discipline not realized — S3).
18. **Read before changing:** [CHANGE_GUIDE](CHANGE_GUIDE.md).
