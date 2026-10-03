# W5A — Starting State

- Approved Master Plan base commit: `e88ebac0dc333251e7be0d98f5c0d9fb6cad4efe` (`feature/phase5-design-expansion`), verified matching local and remote before branching.
- Feature branch: `feature/phase5-w5a-canonical-editor-safety`, created from exactly that commit.
- Worktree clean at branch creation.
- W4C status: officially closed (704/704 certified, no prior W5 implementation).
- Local test environment: no Django installation was present in the sandbox at task start (`ModuleNotFoundError: No module named 'django'` under the default `python3`, which resolved to a Graphify-only venv with no pip). A dedicated virtualenv was created at `/tmp/w5a-venv` and the project's `requirements.txt` packages (excluding `psycopg`, not needed — tests use SQLite) were installed from PyPI. `python manage.py check --settings=shop_core.settings` confirmed clean against the approved base before any W5A change.
- Baseline full-suite run (`apps.storefront_builder.tests`) captured at this exact starting commit, before any W5A code change, to `docs/qa_evidence/storefront_design_engine/phase5/w5a_canonical_editor_safety/../baseline` (see `full_suite_identity_comparison.md` for the reconciled totals against the stated historical reference: 3418 tests / 30 failures / 2 errors / 1 skip).
