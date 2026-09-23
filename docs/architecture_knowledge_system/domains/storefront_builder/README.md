# Domain: storefront_builder (D9) — Storefront Presentation / Builder

```
domain_id: D9
app: apps/storefront_builder
status: CANONICAL
readiness: CONFLICTED
code_baseline: 5883a140
last_verified_against_code: 5883a140
source_phases: Phase 1 / Phase 2 / Phase 4
open_decisions: DR-6
known_risks: H3, M1, M2, M10, M11, M12
```

> **This domain is `CONFLICTED` for documentation** because it is over-documented across four
> generations (families → Universal V2 → V2 phase build → R4/A8/Design-Engine). The **single most
> important navigation aid** is [`GENERATIONS.md`](GENERATIONS.md): the CURRENT vs LEGACY vs
> TEMPLATE/PRESET map. Read it first. **R4 is the current canonical editor** (`r4_editor_enabled`
> defaults `True`); the legacy R3 editor is **fail-closed** rollback-only.

## Pack contents
[GENERATIONS](GENERATIONS.md) ★ · [BOUNDARIES](BOUNDARIES.md) · [ARCHITECTURE](ARCHITECTURE.md) ·
[DATA_MODEL](DATA_MODEL.md) · [SERVICES](SERVICES.md) · [ENTRY_POINTS](ENTRY_POINTS.md) ·
[FLOWS](FLOWS.md) · [STATE_MACHINES](STATE_MACHINES.md) · [DEPENDENCIES](DEPENDENCIES.md) ·
[MUTATION_AUTHORITY](MUTATION_AUTHORITY.md) · [INVARIANTS](INVARIANTS.md) ·
[TESTING](TESTING.md) · [CHANGE_GUIDE](CHANGE_GUIDE.md) · [CODE_MAP](CODE_MAP.md) ·
[HISTORICAL_CONTEXT](HISTORICAL_CONTEXT.md) · [OPEN_DECISIONS](OPEN_DECISIONS.md)

**Not-applicable/folded docs** (recorded here, not empty files): `API_AND_EVENTS.md` (no external
API; no signals; render is internal), `TRANSACTIONS_AND_CONCURRENCY.md` (folded into
[FLOWS](FLOWS.md) + [SERVICES](SERVICES.md): publish/mutate are `@atomic` with optimistic
`edit_revision`), `SECURITY.md` (folded into [ENTRY_POINTS](ENTRY_POINTS.md)/[BOUNDARIES](BOUNDARIES.md):
routes behind `STOREFRONT_LAYOUT_MANAGE`), `TROUBLESHOOTING.md` (folded into [GENERATIONS](GENERATIONS.md)).

## Orientation (condensed)
1. **Owns:** the versioned draft/publish storefront layout (`StorefrontLayout*`,
   `StorefrontPage/Section/Container/Cell`), the R4 editor, A8 ready templates, layout preset
   registry, appearance/theme/palette registries, and the render path.
2. **Does NOT own:** CMS pages/menus/footer content (`content`), catalog data (`catalog`), the
   merchant admin routing shell (`dashboard` registers the routes).
3. **Models:** 7 — see [DATA_MODEL](DATA_MODEL.md).
4. **Canonical services:** `r4_mutation_service` (R4 mutation boundary), `layout_service`
   (draft/publish/restore), `preset_service` (apply presets/A8), `render_service` (render),
   `appearance_authority_service` (typed appearance). See [SERVICES](SERVICES.md).
5. **Which path is CURRENT?** R4. See [GENERATIONS](GENERATIONS.md).
6–18. → linked docs. Smells: H3 (generations), M1 (appearance/palette/theme dup), M2 (footer ×3),
   M10 (dual settings validation), M11 (dual placement media), M12 (dual section-placement). Open DR: DR-6.
