# Rastisi

## Canonical architecture entry point

The authoritative architecture documentation lives in the **Architecture Knowledge System**
under [`docs/architecture_knowledge_system/`](architecture_knowledge_system/):

- Governing rules & Phase 1: [`00_GOVERNING_RULES_AND_PHASE1.md`](architecture_knowledge_system/00_GOVERNING_RULES_AND_PHASE1.md)
- Canonical architecture layer: [`canonical/README.md`](architecture_knowledge_system/canonical/README.md)
- Domain packs: [`domains/`](architecture_knowledge_system/domains/)

Start there for the canonical architecture, the 15 domain packs, change-navigation,
and the documentation validator. Older architecture, storefront-builder, product,
prelaunch, template-reference, reference-kit, prototype, and reference-collection
reports have been relocated under [`docs/archive/`](archive/) as historical evidence
(preserved unchanged; not part of the canonical layer).

## Repository layout

- `backend/` — Django backend
- `frontend/` — Frontend source
- `docs/` — Official documentation (canonical layer under `docs/architecture_knowledge_system/`)
- `prototypes/` — HTML/UI references
- `infra/` — Infrastructure
- `docker/` — Containers
- `scripts/` — Utilities

## Domain architecture

- Public: `https://<store-domain>`
- Admin: `https://<admin-slug>.rastisi.ir/admin-portal/`
