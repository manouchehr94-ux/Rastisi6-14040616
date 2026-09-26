# storefront_builder — Mutation Authority

```
domain_id: D9
code_baseline: 5883a140
open_decisions: DR-6
known_risks: H3, M1, M12
```

## StorefrontLayoutVersion / Sections / Containers / Cells
| Writer | Class | Generation |
|---|---|---|
| `r4_mutation_service` | CANONICAL (R4) | current — single optimistic boundary |
| `layout_service` (publish/draft/restore/clone) | CANONICAL | shared |
| `container_service`, `section_structure_service`, `bootstrap_service`, `preset_service` | SECONDARY (in-domain) | shared/A8 |
| legacy `views.py` mutations | SECONDARY — **fail-closed when R4 enabled** | R3 legacy |

## appearance_config
| Writer | Note |
|---|---|
| `appearance_authority_service` / `storefront_appearance.persistence.persist_store_appearance_manifest` | CANONICAL; draft-only; **mirrors** selectors into `header_config`/`footer_config` (M1 duplication) |

## Cross-domain writes performed BY storefront_builder
- **content placement rows** (`HeroSlide`/`PromotionalBanner`/`StoryRailItem`) — written by
  `layout_service._clone_section_scoped_media` and `media_views` during layout clone/publish.

## Editor-generation rule (H3)
Only ONE editor is the active write surface per Store: R4 when `r4_editor_enabled=True` (default);
R3 mutations fail-closed (Http404) otherwise. See [GENERATIONS](GENERATIONS.md).

## Duplicate write-target note (M1)
Appearance selectors are written in TWO places by design: the typed manifest
(`appearance_config["store_appearance"]`) AND the mirrored `header_config`/`footer_config` keys.
A change to appearance persistence must keep these in sync.
