# RastiSi repository guidance

- For RastiSi codebase investigation, debugging, architecture tracing, dependency analysis, impact analysis, and locating implementation/tests, use the `rastisi-code-map` skill.
- When `graphify-out/graph.json` exists, prefer narrow Graphify queries before broad Grep/Glob/Read scans.
- Graphify is a navigation map, not the source of truth. Verify relevant source files and tests before editing.
- Never commit `graphify-out/` or `.graphify-venv/`.
- Preserve tenant isolation, Store scoping, permissions, and cross-host/domain behavior.
- Git remote for the current development cycle: `origin` = `https://github.com/manouchehr94-ux/Rastisi6-14040616` (owner decision, 2026-10-31; the Windows QA builds are received from it). Do not use `rastisi5` (a separate, older repository).
- Never add, change or remove Git remotes, and never push, merge, deploy, migrate or backfill, without explicit authorization from the owner for that specific action.
