# content — Open Decisions

```
domain_id: D10
code_baseline: 5883a140
```

Full detail: [`../../canonical/ARCHITECTURAL_DECISION_REGISTER.md`](../../canonical/ARCHITECTURAL_DECISION_REGISTER.md).

| DR | Title | Why it affects content | Blocks |
|---|---|---|---|
| **DR-2** | content domain write boundary | content has NO write service; dashboard views mutate all content directly (H2) | introducing a content service; any refactor of content write paths |

## Related findings (not DRs)
- **M2** — footer represented 3 ways (content + storefront_builder + registry).
- **M11** — dual media representation on placements (legacy ImageField + MediaAsset FK).
- **M3** — two "page" concepts (ContentPage vs StorefrontPage).
- **O2** — MED-001 media-cleanup no-ops (intentional).

## Posture
This pack documents the H2 reality precisely (which models, which dashboard view lines) so that if
DR-2 is decided, the migration surface is already mapped. No option is selected.
