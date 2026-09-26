# tools/docs — Documentation validation

Documentation-only tooling for the Architecture Knowledge System. **Does not touch application CI.**

## `validate_architecture_docs.py`
Standard-library-only validator (no external deps; PyYAML is unavailable in this environment, so the
registry is parsed with a minimal line scanner). Run from the repo root:

```bash
python3 tools/docs/validate_architecture_docs.py
```

Checks:
1. Broken internal Markdown links (relative links to missing files).
2. Unknown / duplicate domain IDs (D1..D15) in `architecture_registry.yaml`.
3. Missing required canonical entry-point files.
4. Missing domain-pack `README.md`; expected domain set (15) present.
5. Invalid OPEN decision IDs referenced in docs (must be DR-1..DR-8).
6. Code-path references (`apps/….py`) in canonical + domain docs that do not exist on disk
   (with an allowlist of intentionally-absent files: deleted registries, `apps/blog/urls.py`,
   and the hypothetical `new_gateway.py` example).
7. Canonical graph (`.mmd`) presence.
8. Registry present + structurally parseable.
9. **Canonical-pack readiness disambiguation** (semantic consistency): exactly 15 domain IDs;
   registry has `schema_version` + `field_semantics`; every registry domain carries BOTH
   `phase4_prepack_documentation_readiness` (historical) and `canonical_pack_status` (current);
   `canonical_pack_status` is `CANONICAL` for all 15; the ambiguous generic domain-level
   `status: <readiness>` field is **rejected**; and every domain README uses the agreed schema
   (`canonical_pack_status` + `phase4_prepack_documentation_readiness`, no ambiguous `readiness:`
   or bare `status: CANONICAL`).

Exit code 0 = PASS (warnings allowed), 1 = FAIL (any ERROR).

Latest run output is saved at
`docs/architecture_knowledge_system/VALIDATION_RESULTS.txt`.
