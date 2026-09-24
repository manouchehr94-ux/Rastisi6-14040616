# Phase 1 Baseline

- Source branch: origin/docs/storefront-appearance-convergence
- Approved code baseline ancestor: 93c5afea2ee32bef67cfb5923ffdb13bb61d7930
- Implementation branch: feature/storefront-appearance-convergence-phase1
- Normal precedence: Template DNA -> Store Global -> Page -> Section/Component.
- Explicit local Section variant wins an inherited Store-level family default.
- Historical sections without explicit-local metadata preserve their current inherited/global behavior until edited or migrated.
- Legacy editors remain temporarily and must delegate to canonical state transformations; no route retirement in Phase 1.
- Template Apply remains replacement/reset semantics in Phase 1; content-preserving Switch is not implemented here.
- Lock semantics, live identity publication policy, and full media-retention mechanics remain Phase 2 concerns.
- No new variants, no new renderer, no commerce rewrite.

## Recorded environment and verification (actual outputs)

- Source docs branch HEAD (`origin/docs/storefront-appearance-convergence`): `b5a15272a2488e4cb0d7dbed9a0d5b1697a8da33`
- Implementation branch HEAD (`feature/storefront-appearance-convergence-phase1`): `b5a15272a2488e4cb0d7dbed9a0d5b1697a8da33`
- Approved G2.3 code baseline ancestor SHA: `93c5afea2ee32bef67cfb5923ffdb13bb61d7930` (verified: `git merge-base --is-ancestor 93c5afea… HEAD` → exit 0)
- Python version: `Python 3.12.13`
- Django version: `5.2.17`

### `python manage.py check`

```text
System check identified no issues (0 silenced).
```

(exit code 0)

### `python manage.py makemigrations --check --dry-run`

```text
No changes detected
```

(exit code 0)

## Task-0 non-goals confirmation

- No Task 1 work started; no application Python/template/JS/CSS/test/migration file created or modified.
- Virtual environment provisioned outside the Git worktree (`/projects/rastisi5_phase1_venv`); `requirements.txt` and all tracked files unchanged.
- Implementation branch is based on `origin/docs/storefront-appearance-convergence`, not on `main`; no merge/rebase from `main`.
- Implementation branch is not pushed at this gate.
