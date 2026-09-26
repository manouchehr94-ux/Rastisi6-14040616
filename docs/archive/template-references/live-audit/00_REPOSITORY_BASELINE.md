# 00 — Repository Baseline (Verified Facts)

**Audit date/time:** 2026-08-09 (session start). All facts below were verified directly against the checked-out repository; none are guessed.

## Repository identity

- Official repo (per master prompt): `https://github.com/manouchehr94-ux/RastiSi4`. Verified remote in this working copy: `origin = https://github.com/manouchehr94-ux/RastiSi4` (matches — this is genuinely the correct repository, not a same-named fork).
- Working copy root: `/home/user/RastiSi4` (this is a cloud/remote execution session, not the Windows path `D:\Projects\siteSaz3` mentioned in the master prompt's "known context" — that path is not present/relevant in this environment; noted, not treated as a discrepancy since the master prompt says to verify the actual repo rather than assume a local path).
- Current branch: `claude/jolly-fermat-ypr2ff` (the branch this task is required to develop on).
- HEAD at audit start: `4f424453df73f22265ffda75283bb0bbe92c0aae` — "Merge pull request #7 from manouchehr94-ux/claude/rastisi-storefront-builder-final-review".
- `git status`: clean working tree, nothing to commit, no unrelated in-progress user changes present.
- No upstream tracking branch was configured for `claude/jolly-fermat-ypr2ff` at session start (`git rev-parse --abbrev-ref --symbolic-full-name @{u}` failed with "no upstream configured"). It will be set on first push (`git push -u origin claude/jolly-fermat-ypr2ff`) only when explicitly authorized later.

## Stack versions (verified, not assumed)

- **Python:** 3.11.15 (`python3 --version`).
- **Django:** `Django>=5.2,<6` pinned in `requirements.txt`; `shop_core/settings.py` header confirms it was generated with Django 5.2.16.
- **Database:** SQLite by default for local dev/tests (`shop_core/settings.py` comment + `build_database_config`); PostgreSQL in production via `psycopg[binary]>=3.2,<4` (env-driven `DATABASE_URL`).
- **Other pinned deps:** `jdatetime` (Persian calendar), `Pillow` (image processing), `requests`, `cryptography`, `beautifulsoup4`, `PySocks`, `dnspython` (real DNS TXT/CNAME lookups for custom-domain verification).
- **No Node/JS package manager in this repo.** No `package.json` found anywhere in the tree. The storefront is server-rendered Django templates + plain CSS/JS static files (no bundler, no npm build step). Confirmed by absence of `package.json` and by `static/`/`apps/*/static/` containing plain `.css`/`.js` files directly.
- **Test runner:** Django's built-in test runner (`manage.py test`). No `pytest.ini`, `pyproject.toml` pytest config, or `conftest.py` found. 14 apps each have a `tests/` package (`apps/{catalog,stores,orders,sms,customers,content,notifications,billing,cart,dashboard,storefront_builder,core,subscriptions,portal}/tests`).
- **CI:** No `.github/` directory exists in this repository — there are no GitHub Actions workflows to satisfy or break.
- **Migrations:** 134 non-`__init__.py` migration files across `apps/*/migrations/`.

## Installed apps (from `shop_core/settings.py:INSTALLED_APPS`)

`apps.core`, `apps.catalog`, `apps.customers`, `apps.cart`, `apps.orders`, `apps.dashboard`, `apps.blog`, `apps.sms`, `apps.content`, `apps.storefront_builder`, `apps.stores`, `apps.subscriptions`, `apps.billing`, `apps.portal`, `apps.notifications` (plus Django's own contrib apps).

## Middleware order (tenant-relevant, `shop_core/settings.py`)

```
SecurityMiddleware
apps.stores.middleware.StoreResolutionMiddleware   ← runs before Session/Auth, by design (see architecture docs)
apps.portal.middleware.PlatformHostRoutingMiddleware
SessionMiddleware
CommonMiddleware
CsrfViewMiddleware
AuthenticationMiddleware
MessageMiddleware
XFrameOptionsMiddleware
```

## Pre-existing repository instructions and architecture documents read for this audit

No root-level `AGENTS.md`, `CLAUDE.md`, or `README.md` exists in this repository. The applicable "repository instructions" are the extensive `docs/` tree instead. Documents read in full or in relevant part before starting Phase 1:

- `docs/docs/product/architecture/SAAS_ARCHITECTURE.md` (720 lines) — tenant/Store resolution, ownership rules, isolation layering. Read in full.
- `docs/reports/STOREFRONT_TEMPLATE_AND_BUILDER_AUDIT.md`, `..._ARCHITECTURE_PLAN.md`, `..._IMPLEMENTATION_ROADMAP.md` — read in full. **Critical finding, see below: these three documents are dated 2026-08-06 and are now materially out of date.**
- `docs/docs/product/architecture/SAAS_DOMAIN_DECISIONS.md` (4508 lines) — referenced/spot-checked for ADR citations surfaced by the above documents (ADR-10, ADR-25), not read end-to-end at this stage.
- `docs/docs/product/00_PROJECT_MASTER_REFERENCE.md` (2189 lines) — **not read end-to-end**; the storefront-builder audit document itself flags this master reference as stale on the Page Builder topic (§14/notes), so it was not treated as authoritative for this task without independent code verification.

### ⚠️ Critical finding: the three most relevant planning documents in `docs/reports/` are stale

`STOREFRONT_TEMPLATE_AND_BUILDER_AUDIT.md` / `_ARCHITECTURE_PLAN.md` / `_IMPLEMENTATION_ROADMAP.md` describe the codebase as of commit `d830f5f` (2026-08-06) and explicitly list numerous capabilities as `❌ ABSENT` (Merchant Collections, per-section Data Source, Responsive per-section settings, a Template+Preset system, atomic reorder, a shared preview/storefront page shell, header/footer config validation, `collapsed_in_editor`).

**`git log --oneline d830f5f..HEAD` (61 commits) shows every one of those gaps has since been implemented**, in the same order the roadmap itself proposed (its own Phase A → E labels are visible verbatim in commit messages: `collections: add MerchantCollection models and permission`, `storefront-builder: add validated product section data-source contract`, `storefront-builder: add responsive visibility and column controls`, `storefront-builder: make reorder operations atomic`, `storefront-builder: validate header and footer configuration`, `storefront-builder: share preview and live storefront shell`, `storefront-builder: add persistent editor collapse state`, `storefront-builder: add visual template system (10 structurally distinct templates)`, `storefront-builder: add 20-palette gallery with base+override architecture`).

**Conclusion for this task: those three documents must be treated as historical record only, not as current-state evidence.** Every claim used in `01_REPOSITORY_ARCHITECTURE_AND_GAPS.md` is re-verified directly against the current code (with file:line citations), not copied from those documents. This baseline note exists so a future reader does not repeat the mistake of trusting the dated audit over the live repository.

## Scope note on the local Windows path

The master prompt's "known project context" states an expected local Windows path `D:\Projects\siteSaz3`. This session runs in a Linux cloud container with the repository already cloned to `/home/user/RastiSi4` (and mirrored read-only for GitHub-API purposes at `/workspace/rastisi4`, HEAD-identical). There is no discrepancy to resolve — the two are simply the same GitHub repository checked out in different environments (owner's laptop vs. this session's container) — no action needed.
