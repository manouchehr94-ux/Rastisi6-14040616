# P5-W4C — All-50 Browser Certification — Implementation Plan

**Repair status:** Independent Review Repair Round 1 applied (CRITICAL 0 /
IMPORTANT 5, all five addressed below). Previous design head:
`bb04401a16dee905926e7ad0f6dfd0e9322a4e40`. This revision corrects: (1) the
browser-certification authority, (2) the Theme matrix cardinality, (3) an
explicit state-isolation contract, (4) the mandatory Home gallery (Desktop +
Mobile), (5) all TODO/TBD placeholders and the RED-test contract.

**Certified official base:** `3a4fe9070584655548bae5a9bb574f3415bbf580`
**Branch:** `feature/phase5-w4c-all50-certification`
**Companion document (read first):**
`docs/qa_evidence/storefront_design_engine/phase5/w4_certification/w4c_harness_inventory.md`
— full source citations, the complete 50-Template table, and the exact
extension-seam facts (§10 of that document) this plan's decisions are built
on.

**Status of this document:** plan/inventory only. No production code, Django
test code, or QA harness code changes are authorized by this document. Every
task below is deliverable only after a separate authorization round.

---

## 0. Scope recap

- Goal: real browser closure gate for **all 50** current merchant-facing Ready
  Templates (not a representative subset) — including Theme interaction,
  which must also reach all 50 (Repair Round 1, IMPORTANT 2).
- **Browser certification authority:** `tools/storefront_builder_r4_qa/run.mjs`
  — extended through one new, opt-in, additive `manifest.w4c`-gated block.
  No second harness.
- **Django orchestration authority:**
  `apps/storefront_builder/management/commands/qa_storefront_builder_r4.py`
  — extended with one new `--w4c-all50` flag and two new manifest keys
  (`w4c`, `w4c_fixture`), following the exact shape of the existing
  `--phase3`/`phase3_fixture` extension point.
- **`capture_ready_template_previews.py` role:** Gallery capture only —
  unchanged, never the certification PASS/FAIL authority, never invoked from
  within the `--w4c-all50` run.
- Evidence root: `docs/qa_evidence/storefront_design_engine/phase5/w4_certification/`.
- W5 remains frozen until this workstream merges with zero unresolved
  CRITICAL/IMPORTANT findings.

---

## 1. Exact matrix cardinality (repaired)

```
Base matrix:   50 Templates x 4 page classes (Home, Listing, PDP, Cart) x 3 viewports (Desktop 1440x900, Tablet 768x1024, Mobile 390x844)
             = 600 certification cells

Theme matrix:  Tier 1 (breadth, ALL 50)  — 1 deterministic occasion per Template (cycled nowruz/ramadan/muharram, see table below) x balanced intensity x Desktop only x 50 Templates = 50 cells
               Tier 2 (depth)            — 2 Templates (warm_boutique, beauty_dew) x 3 occasions x 3 intensities x 3 viewports = 54 cells
             = 104 additional cells

TOTAL:         704 certification cells
```

### 1.1 Tier 1 exact occasion assignment (deterministic, `_SPECS` source order, cycling `nowruz -> ramadan -> muharram`)

Computed via `for i, s in enumerate(_SPECS): occasion = ["nowruz","ramadan","muharram"][i % 3]`
— reproducible from source, never randomized at run time:

| Template key | Occasion | Template key | Occasion | Template key | Occasion |
|---|---|---|---|---|---|
| editorial_jewelry | nowruz | tower_department | nowruz | almas_luxury | nowruz |
| dense_marketplace | ramadan | beauty_dew | ramadan | roosta_zigzag | ramadan |
| warm_boutique | muharram | fashion_promo_catalog | muharram | mother_utility | muharram |
| premium_leather | nowruz | horizon_story | nowruz | aftab_price | nowruz |
| dark_digital | ramadan | mina_community | ramadan | mist_quiet | ramadan |
| cedar_home | muharram | silk_editorial | muharram | night_catalog | muharram |
| street_drop | nowruz | tuska_bento | nowruz | watchmaker_round | nowruz |
| premium_leather_noir | ramadan | rayan_tech | ramadan | kite_playful | ramadan |
| search_market | muharram | laleh_play | muharram | pine_eco | muharram |
| playful_lifestyle | nowruz | city_classic | nowruz | mirror_beauty | nowruz |
| utility_catalog | ramadan | collection_index | ramadan | charcoal_grill | ramadan |
| artisan_grain | muharram | kamand_artisan | muharram | calligraphy_paper | muharram |
| pixel_play | nowruz | | | harbor_imports | nowruz |
| simorgh_market | ramadan | | | parnian_editorial | ramadan |
| coastal_product | muharram | | | racer_tech | muharram |
| literary_catalog | nowruz | | | ferdowsi_department | nowruz |
| gallery_minimal | ramadan | | | anniversary_mosaic | ramadan |
| handmade_luxe | muharram | | | | |
| niloufar_glass | nowruz | | | | |
| tool_finder | ramadan | | | | |
| green_workshop | muharram | | | | |

(50 rows total, 17 `nowruz` / 17 `ramadan` / 16 `muharram` — exact counts,
verified programmatically.)

No reduction of the 600-cell base matrix was found to be architecturally
required (harness inventory §5). If execution later discovers a genuine
architectural impossibility for one page class on one Template, that specific
cell is marked `BLOCKED — <reason>` in the JSON matrix and escalated to
Architect review; the matrix is never silently shrunk.

---

## 2. Shared certification fixture

- **Store:** `rasti-mode-demo`.
- **Seed command:** `python manage.py seed_ready_template_fashion_demo`
  (idempotent — safe to re-run before each execution batch).
- **PDP fixture product:** the first product returned by
  `Product.objects.filter(store=store, product_type=Product.ProductType.VARIABLE).order_by("id").first()`
  from the seeded catalog — deterministic (ordered by `id`, not random),
  guaranteed to exist because the seed command's `_seed_variants` step seeds
  at least one size/color-variable product.
- **Cart fixture:** add that same deterministic product (quantity 1) via the
  canonical `cart:add` route for every Cart cell — never direct DB session
  manipulation (repaired isolation contract, §5).
- **Theme:** applied/cleared via direct Python calls to the canonical
  `appearance_authority_service.apply_theme`/`clear_theme` functions (the
  exact same functions the R4 editor's own `theme.apply`/`theme.clear`
  allowlisted mutation types ultimately delegate to — harness inventory
  §11.4), operating on a Draft obtained via
  `layout_service.get_or_create_draft` and published via
  `layout_service.publish` (§3.6) — never through the R4 HTTP
  mutation-dispatch layer itself (`r4_mutation_service.apply_mutation`'s
  revision-check/allowlist machinery exists for the browser-mediated editor
  session; this batch orchestrator has direct ORM/service access and needs
  none of it), never a direct write to a published version, never a second
  Theme mechanism.
- **QA staff user:** `w4c_qa_owner`, created once (idempotent — skip if it
  already exists) before the campaign, exactly mirroring the repo's own
  established precedent for a Store-scoped QA owner (e.g.
  `phase3_qa_owner`, `2026-09-06-storefront-vertical-slice-phase3-implementation-plan.md`):
  ```
  python manage.py shell -c "from django.contrib.auth import get_user_model; from apps.stores.models import Store, StoreMembership; from django.utils import timezone; s=Store.objects.get(slug='rasti-mode-demo'); u,_=get_user_model().objects.get_or_create(username='w4c_qa_owner', defaults={'is_staff': True, 'is_active': True}); u.set_unusable_password(); u.save(update_fields=['password']); StoreMembership.objects.get_or_create(store=s, user=u, defaults={'role': StoreMembership.Role.OWNER, 'status': StoreMembership.MembershipStatus.ACTIVE, 'accepted_at': timezone.now()})" --settings=shop_core.settings
  ```
  `--username w4c_qa_owner` is still required at the `qa_storefront_builder_r4.py`
  argparse level (unconditionally `required=True`, unchanged interface —
  §3.9 does not special-case this away) because `handle()` unconditionally
  builds a session cookie for the legacy path's own needs before branching
  on `--w4c-all50`; the resulting cookie value is simply never included in
  any W4C manifest (§3.7/§5).
- Same merchant data used for every one of the 50 Templates — no per-template
  fixture variation, no fixture IDs written into any `_RecipeSpec`.

---

## 3. Canonical harness extension target + exact control flow (repaired — Important 1, Round 2)

**Repair note (Round 1):** the original plan proposed extending
`capture_ready_template_previews.py` into the certification authority,
rejected because the authoritative plan names
`tools/storefront_builder_r4_qa/run.mjs` (and/or `tools/storefront_builder_qa/`).

**Repair note (Round 2):** Round 1's corrected target was accepted, but left
the apply/publish/verify transition and the Python↔Node invocation loop
undefined, and cited `lpr.get_layout_preset(key).version` as sufficient
publish-proof (it is not — it only proves the registry definition exists,
never that it is published on the Store). This section now defines one
exact, executable control flow, source-grounded in harness inventory §11.

### 3.1 Division of authority (binding)

- **Python (`qa_storefront_builder_r4.py`) owns every Store-state
  transition:** applying a preset to a Draft, publishing it, applying/
  clearing a Theme, and verifying the REAL published result via
  `StorefrontLayout.published_version` — never the registry alone.
- **Node (`run.mjs`) owns only browser assertions** for one already-published
  Template's public cells, for one invocation, then exits — it never calls
  into Django, never reconstructs a preset, never patches a model.
- No second preset-application path, no Node-side preset reconstruction, no
  direct model patching from either side.

### 3.2 Exact Python ⟷ Node loop (repaired — Round 3, Important 1: base and Theme are separate invocations)

**Repair note:** the Round 2 draft's loop folded a Template's Theme cell
into the SAME node invocation as its 12 base cells, while §5.3 (unchanged
since Round 2) independently described Theme cells as their own
apply/publish/invoke/clear cycle — a genuine contradiction. The corrected
loop below makes base and Theme two fully separate kinds of invocation,
never merged into one manifest or one process:

```
_prepare_w4c_certification_fixture(store)        # 3.3 -- NOT _prepare_r4_sandbox
start one local runserver on the campaign's fixed port (existing subprocess pattern, reused unchanged)
w4c_fixture = _build_w4c_fixture(store)          # 50 key/version pairs, PDP product id,
                                                  # Tier-1 occasion map (section 1.1), Tier-2 pair
campaign_root = CAMPAIGN_REPORT_ROOT             # section 3.9 -- one fixed, explicit path for the whole campaign
matrix_path = campaign_root / "matrix.json"
_validate_or_init_campaign_matrix(matrix_path)   # section 3.9 -- fails fast on certified_base_sha/schema_version mismatch

# ---------- BASE: 50 invocations, 12 cells each = 600 cells ----------
for key in selected_keys (deterministic _SPECS order, or --only subset):
    preset = lpr.get_layout_preset(key)
    _apply_and_verify_published(store, preset)                     # section 3.4
    base_manifest_path = _write_w4c_base_manifest(                 # mode="base", NO theme_cell field at all
        base=stable_w4c_manifest, key=preset.key, version=preset.version,
        cells=["home", "listing", "pdp", "cart"] x [desktop, tablet, mobile],
        report_dir=campaign_root,
        result_path=campaign_root / "w4c-results" / "base" / f"{key}.json",
        log_path=campaign_root / "logs" / "base" / f"{key}.log",
    )
    exit_code = self._run_logged([node, run_mjs_path, base_manifest_path],
                                  cwd=r4_tool_dir, log_path=campaign_root / "logs" / "base" / f"{key}.log")
    base_result = json.loads((campaign_root / "w4c-results" / "base" / f"{key}.json").read_text())
    _merge_into_matrix_json(matrix_path, key, page_classes=base_result)   # section 3.10, atomic read-merge-write
    os.unlink(base_manifest_path)
    # ordinary assertion FAILures inside base_result do not stop the loop --
    # the campaign continues so the run produces a complete failure inventory (Important 2C)

# ---------- THEME TIER 1: 50 invocations, 1 cell each = 50 cells ----------
for key in selected_keys:
    occasion, intensity = w4c_fixture["tier1_occasions"][key], "balanced"
    _run_one_theme_cell(store, key, occasion, intensity, viewport="desktop", campaign_root=campaign_root, matrix_path=matrix_path)

# ---------- THEME TIER 2: up to 54 invocations, 1 cell each -- FILTERED BY selected_keys (Important 1, Round 4) ----------
TIER2_KEYS = ("warm_boutique", "beauty_dew")
for key in selected_keys:                    # NEVER an unconditional ("warm_boutique", "beauty_dew") loop --
    if key not in TIER2_KEYS:                # a --only batch that excludes both Tier-2 keys must run ZERO Tier-2 cells
        continue
    for occasion in ("nowruz", "ramadan", "muharram"):
        for intensity in ("subtle", "balanced", "strong"):
            for viewport in ("desktop", "tablet", "mobile"):
                _run_one_theme_cell(store, key, occasion, intensity, viewport, campaign_root, matrix_path)

run final 704-cell aggregator (plan section 15)
finally: stop runserver, restore SQLite DB backup (existing lifecycle, reused unchanged)
```

```python
def _run_one_theme_cell(self, store, key, occasion, intensity, viewport, campaign_root, matrix_path):
    result_path = campaign_root / "w4c-results" / "theme" / f"{key}__{occasion}__{intensity}__{viewport}.json"
    log_path = campaign_root / "logs" / "theme" / f"{key}__{occasion}__{intensity}__{viewport}.log"
    try:
        preset = lpr.get_layout_preset(key)
        self._apply_and_verify_published(store, preset)            # confirm the Template itself is still published
        self._verify_theme_is_none(store)                          # confirm starting from a clean baseline
        draft = layout_service.get_or_create_draft(store)
        appearance_authority_service.apply_theme(version=draft, component_key=THEME_CATALOG[occasion], intensity=intensity)
        layout_service.publish(store)
        self._verify_published_theme(store, occasion, intensity)   # real published-state check, section 3.4-style
        theme_manifest_path = self._write_w4c_theme_manifest(       # mode="theme", exactly ONE cell
            base=stable_w4c_manifest, key=key, version=preset.version,
            occasion=occasion, intensity=intensity, viewport=viewport,
            result_path=result_path, log_path=log_path,
        )
        exit_code = self._run_logged([node, run_mjs_path, theme_manifest_path], cwd=r4_tool_dir, log_path=log_path)
        theme_result = json.loads(result_path.read_text())
        self._merge_theme_into_matrix_json(matrix_path, key, occasion, intensity, viewport, theme_result)
        os.unlink(theme_manifest_path)
    finally:
        self._theme_cleanup_and_verify(store)   # section 3.6 -- ALWAYS runs; raising here is BLOCKING (Important 2C)
```

Node is invoked **154 times total for a FULL 50-key campaign** — **50 base
invocations** (one per Template, each covering exactly 12 cells) **+ 104
Theme invocations** (one per Theme cell, each covering exactly 1 cell) — a
fresh browser process per invocation (the same anti-cache-leak isolation
`capture_ready_template_previews.py` already established as necessary).
**Certification cells for a full campaign remain exactly 704** (600 base +
50 Tier-1 + 54 Tier-2) — invocation count and cell count are two different
numbers by design (12 cells share one base invocation; each Theme cell gets
its own invocation), and this document never conflates them again. This
mirrors the existing `_run_logged`/`subprocess.Popen` mechanism exactly
(harness inventory §10.B) — called 154 times in two loops instead of once.

**Repair note (Round 4, Important 1):** the prior draft's Tier-2 loop
(`for key in ("warm_boutique", "beauty_dew"): ...`) ran unconditionally,
regardless of `--only` — a `--only editorial_jewelry` batch would still have
executed all 54 Tier-2 cells for two Templates never selected, breaking
subset semantics, resumability, and no-overwrite-of-PASSed-evidence. The
corrected loop above iterates `selected_keys` and `continue`s past any key
not in `TIER2_KEYS`, so Tier-2 cells run ONLY when a Tier-2 key is actually
in the batch. Exact cardinalities per invocation shape:

| `--only` selection | base cells | Tier-1 Theme | Tier-2 Theme | total cells | Node invocations |
|---|---|---|---|---|---|
| `editorial_jewelry` (a non-Tier-2 key) | 12 | 1 | 0 | 13 | 2 (1 base + 1 Tier-1) |
| `warm_boutique` | 12 | 1 | 27 | 40 | 29 (1 base + 1 Tier-1 + 27 Tier-2) |
| `beauty_dew` | 12 | 1 | 27 | 40 | 29 |
| full 50-key campaign (no `--only`) | 600 | 50 | 54 | 704 | 154 |

A `--only` batch never executes a Theme cell for a key it did not select —
including Tier-2 cells for `warm_boutique`/`beauty_dew` when neither is in
that batch's `selected_keys` — so a later, unrelated `--only` batch can
never overwrite an already-recorded Tier-2 result file (§3.9's unique
per-cell paths mean it would not even collide if it somehow tried).

Per Important 2C: an ordinary assertion FAILure inside any base or Theme
cell's result does NOT stop the campaign — remaining Templates/cells still
run, so the campaign produces a complete failure inventory. The ONE
exception is `_theme_cleanup_and_verify` (the `finally` block above)
raising — that is BLOCKING and halts the entire campaign immediately
(§3.6), because it means Store Theme state can no longer be trusted for any
subsequent cell.

### 3.3 `_prepare_w4c_certification_fixture` — bypasses the legacy sandbox

New method on the same `Command` class, invoked only when `--w4c-all50` is
set, in place of `_prepare_r4_sandbox` (never both):

- Ensures `rasti-mode-demo` exists and is current via
  `call_command("seed_ready_template_fashion_demo")` (idempotent, §2) —
  never wipes `layout.published_version`/`draft_version` and never deletes
  `Section`/`Container` rows the way `_prepare_r4_sandbox` does (confirmed
  destructive at `qa_storefront_builder_r4.py:422-512`, harness inventory
  §11.3 — that method is correct for the legacy R4 smoke suite's own need to
  OBSERVE a from-scratch publish transition, and is exactly wrong for W4C,
  which needs a real, Ready-Template-published starting state per Template).
- Reuses the existing SQLite backup/restore safety lifecycle unchanged (the
  same backup-before/restore-after wrapping every other `qa_storefront_builder_r4`
  invocation already uses).
- When `--w4c-all50` is NOT set, this method is never called and
  `_prepare_r4_sandbox` runs exactly as it does today — byte-for-byte
  unchanged non-W4C behavior.

### 3.4 `_apply_and_verify_published` — exact apply/publish/verify sequence

```python
def _apply_and_verify_published(self, store, preset):
    preset_service.apply_preset_with_checkpoint(store, preset)   # Draft-only, never touches Published
    layout_service.publish(store)                                # flips Draft -> Published
    layout = StorefrontLayout.objects.get(store=store)
    pv = layout.published_version
    if pv is None or pv.status != pv.Status.PUBLISHED:
        raise CommandError(f"W4C: {preset.key} v{preset.version} has no valid published version")
    template = (pv.template_provenance or {}).get("template") or {}
    if template.get("key") != preset.key or template.get("version") != preset.version:
        raise CommandError(f"W4C: {preset.key} v{preset.version} did not verify as published (found {template})")
```

**Repair note (Round 3, Important 2D):** the Round 2 draft computed
`template = (pv.template_provenance or {})...` BEFORE checking `pv is
None`, so a `None` published version would raise an uncontrolled
`AttributeError` rather than the intended `CommandError` — the exact bug the
Independent Architect flagged. The corrected ordering above checks `pv is
None`/`pv.status` FIRST, raises the controlled error immediately if either
fails, and only then dereferences `pv.template_provenance`. This is the
exact, source-verified chain (harness inventory §11.1–11.2):
`apply_preset_with_checkpoint` is Draft-only by its own docstring guarantee;
`publish` performs the pointer swap with no `edit_revision` check, so the
two calls in sequence are sufficient; verification reads
`StorefrontLayout.published_version.template_provenance["template"]`
(written verbatim by `apply_preset`'s `build_template_provenance` call),
never the registry alone. This same None-then-attribute ordering is applied
consistently in `_verify_published_theme`/`_verify_theme_is_none` (§3.6)
below.

### 3.5 Host resolution — `_build_manifest`'s single-`host` bug, fixed (Round 2 Important 3, detailed in §3.8)

Confirmed exact bug (harness inventory §11.5): `origin`, `public_url`, and
`resolver_host` are today all derived from ONE `host` variable gated by the
SAME `showcase` boolean — non-showcase mode hardcodes `host = "127.0.0.1"`
and `resolver_host = None` unconditionally, so no existing caller can make
`public_url` resolve to the customer-facing Store host. The fix extends that
same computation with a third, mutually-exclusive branch:

```python
if showcase:
    host = f"{store.admin_subdomain}{self.SHOWCASE_QA_HOST_SUFFIX}"
elif w4c_all50:
    host = f"shop-{store.admin_subdomain}.{settings.RASTISI_ADMIN_DOMAIN_SUFFIX}"
else:
    host = "127.0.0.1"
origin = f"http://{host}:{port}"
resolver_host = host if (showcase or w4c_all50) else None
public_url = f"{origin}/"
```

`--w4c-all50` and `--showcase` are validated mutually exclusive in
`handle()` (a `CommandError` if both are passed), so this is a clean 3-way
branch, never an ambiguous combination. Chromium in `run.mjs` receives
`--host-resolver-rules=MAP {resolver_host} 127.0.0.1` exactly as it already
does for `showcase` mode — no new Chromium launch mechanism.

### 3.6 Theme cleanup ownership — Python only, failure-safe

```python
def _verify_theme_is_none(self, store):
    layout = StorefrontLayout.objects.get(store=store)
    pv = layout.published_version
    if pv is None or pv.status != pv.Status.PUBLISHED:
        raise CommandError("W4C: no valid published version -- cannot verify Theme state")
    manifest = load_store_appearance_manifest(pv)
    if manifest.selections.get("theme") != "theme.none.v1":
        raise CommandError(f"W4C: expected theme.none.v1, found {manifest.selections.get('theme')}")

def _verify_published_theme(self, store, occasion_component_key, intensity):
    layout = StorefrontLayout.objects.get(store=store)
    pv = layout.published_version
    if pv is None or pv.status != pv.Status.PUBLISHED:
        raise CommandError("W4C: no valid published version -- cannot verify Theme state")
    manifest = load_store_appearance_manifest(pv)
    if manifest.selections.get("theme") != occasion_component_key \
       or manifest.settings.get("theme", {}).get("intensity") != intensity:
        raise CommandError(f"W4C: Theme did not verify as published ({occasion_component_key}/{intensity})")

def _theme_cleanup_and_verify(self, store):
    draft = layout_service.get_or_create_draft(store)
    appearance_authority_service.clear_theme(version=draft)
    layout_service.publish(store)
    self._verify_theme_is_none(store)   # raises CommandError, never AttributeError, per section 3.4's ordering fix
```

Called from a Python `try/finally` around each Theme cell's own apply+
publish+navigate+assert sequence (§3.2's `_run_one_theme_cell`) — cleanup
runs whether the browser assertion step passed, failed, or raised. If
`_theme_cleanup_and_verify` itself raises, the entire `--w4c-all50` run
halts immediately (no further base or Theme cells execute, per §3.2's
Important-2C exception) and the run is reported `BLOCKED`, with an exact,
real verification query (`load_store_appearance_manifest(pv).selections["theme"]`,
harness inventory §11.4) rather than an unverified assumption. Both helper
functions apply the same `pv is None`-checked-first ordering as
`_apply_and_verify_published` (§3.4) — no path here can raise an
uncontrolled `AttributeError` in place of a `CommandError`.

### 3.7 `tools/storefront_builder_r4_qa/run.mjs` — browser certification authority, one invocation per base Template OR per Theme cell, no forced exit

Exact insertion point (source-verified, harness inventory §10): a NEW,
separate entry path guarded by `manifest.w4c` at the very top of the
script's dispatch, BEFORE the existing `main()`'s 13 unconditional core
scenarios run — because a `--w4c-all50` invocation of `run.mjs` runs ONLY
one W4C browser-assertion function for its one manifest (`mode: "base"` or
`mode: "theme"`, §3.2), never the R4 mutation/undo/redo/publish smoke suite
(those 13 scenarios assume the `_prepare_r4_sandbox` fixture, which W4C
never creates, §3.3):

```js
const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
if (manifest.w4c) {
  if (manifest.mode === 'base') {
    await w4cBaseCertification(manifest);
  } else if (manifest.mode === 'theme') {
    await w4cThemeCertification(manifest);
  } else {
    throw new Error(`unknown W4C manifest.mode: ${manifest.mode}`);
  }
  // process.exitCode set inside each function's own finally block below -- never process.exit() here or inside them
} else {
  await main();   // existing, completely unchanged
}
```

**Repair note (Round 3, Important 2A/2B):** the Round 2 draft called
`process.exit()` inside a single `w4cAll50Certification` function. The
Independent Architect rejected this: a forced `process.exit()` can bypass
browser/context cleanup and leave orphaned Chromium child processes or
unwritten evidence across a 154-invocation campaign. Both new functions
below use structured `try/finally` cleanup and only ever SET
`process.exitCode` (a plain integer property Node reads on natural event-loop
drain) — never call `process.exit()` directly:

```js
async function w4cBaseCertification(manifest) {
  const browser = await chromium.launch({ /* existing launch args pattern, host-resolver-rules from manifest.resolver_host */ });
  const openContexts = [];
  let result = { key: manifest.active_key.key, version: manifest.active_key.version, page_classes: {} };
  try {
    for (const pageClass of ['home', 'listing', 'pdp', 'cart']) {
      for (const viewport of ['desktop', 'tablet', 'mobile']) {
        const context = await browser.newContext({ viewport: VIEWPORTS[viewport] });   // cookie-less, anonymous -- section 5
        openContexts.push(context);
        result.page_classes[pageClass] = result.page_classes[pageClass] || {};
        result.page_classes[pageClass][viewport] = await runCell(context, pageClass, viewport, manifest);
      }
    }
  } finally {
    for (const context of openContexts) { await context.close(); }
    await browser.close();
    fs.writeFileSync(manifest.result_path, JSON.stringify(result, null, 2), 'utf8');
    process.exitCode = Object.values(result.page_classes).some(pc => Object.values(pc).some(v => v.result === 'FAIL')) ? 1 : 0;
  }
}

async function w4cThemeCertification(manifest) {
  const browser = await chromium.launch({ /* same pattern */ });
  let result = { key: manifest.active_key.key, occasion: manifest.active_key.occasion,
                  intensity: manifest.active_key.intensity, viewport: manifest.active_key.viewport };
  let context;
  try {
    context = await browser.newContext({ viewport: VIEWPORTS[manifest.active_key.viewport] });   // cookie-less
    Object.assign(result, await runThemeCell(context, manifest));
  } finally {
    if (context) { await context.close(); }
    await browser.close();
    fs.writeFileSync(manifest.result_path, JSON.stringify(result, null, 2), 'utf8');
    process.exitCode = result.result === 'FAIL' ? 1 : 0;
  }
}
```

Both functions:
- Use a fresh, **cookie-less** `browser.newContext()` for every cell — no
  `manifest.session` field exists or is injected in W4C mode at all
  (Important 2, §5). Python needs no authenticated browser action for W4C
  (all Store-state transitions are ORM/service calls, §3.1), so the
  manifest these functions receive never carries a `session` key.
- PDP/Cart mutation cells (`cart:add`/`cart:item-update`/`cart:item-remove`)
  use `context.request.post(...)`/`context.request.get(...)` (Playwright's
  `APIRequestContext`, part of the already-shared `playwright-core`
  dependency) — copied from `tools/storefront_builder_qa/public_w1_qa.mjs`'s
  own already-proven anonymous cart-flow implementation, adapted here, not
  duplicated into a second file.
- Write their own result file at the EXACT path `manifest.result_path`
  supplied by Python (§3.2/§3.9 — never a shared/reused filename across
  invocations), via a plain `fs.writeFileSync(...)`, the same ad hoc way
  `metrics.json`/`task6_diagnostics.json` already are (no shared writer
  function exists to call, confirmed absent by grep) — Python reads this
  file and merges it into the combined `matrix.json`.
- Close every context and the browser in a `finally` block BEFORE writing
  the result file and setting `process.exitCode` — cleanup is guaranteed
  even if `runCell`/`runThemeCell` throws.
- Zero lines of the existing 15 scenarios, the phase3/showcase blocks, or
  `main()` itself are touched — the `if (manifest.w4c) {...} else { await
  main(); }` guard at the very top, unchanged from Round 2, is the only
  change to the file's control flow; the `mode` dispatch inside the
  `manifest.w4c` branch is new but self-contained.

### 3.8 `apps/storefront_builder/management/commands/capture_ready_template_previews.py` — Gallery capture only, unchanged, and NOT the Home-gallery source

Zero code changes. Confirmed (harness inventory §11.6): its own canonical
Home-Desktop capture viewport is **1440×1100**, not W4C's certification
viewport **1440×900** — the two are not interchangeable. The mandatory
100-asset Home gallery (§12) is therefore sourced directly from the
`--w4c-all50` certification cells themselves (§4, which already run Home at
Desktop 1440×900 and Mobile 390×844), never from this command's output.
This command is used only as a separate, deliberately-invoked,
stale-check-gated step (§12/§17 Task 6) for the DIFFERENT, pre-existing
responsibility of refreshing `apps/storefront_builder/static/ready_template_previews/<key>/v<version>.{webp,meta.json}`
— the `w4c` code path in `run.mjs` never reads or writes anything under
that path.

No other file under `apps/`, `tools/`, or `migrations/` is touched by this
extension.

### 3.9 Campaign report root, unique result/log paths, and matrix schema guard (new — Round 3, Important 3)

**Exact, stable, external campaign root (chosen now, not left to operator
discretion):**

```
CAMPAIGN_REPORT_ROOT = /var/tmp/rastisi_w4c_campaign
```

External to the repository (never noisy in `git status` mid-campaign — 154
log files + 154 result JSONs are scratch, not evidence, until curated).
Every one of the 154 invocations in ONE campaign passes
`--report-dir /var/tmp/rastisi_w4c_campaign` (via `qa_storefront_builder_r4.py`'s
existing `--report-dir` flag) — this is the single invariant that keeps them
all reading/writing the SAME `matrix.json`. Only at the end (§17 Task 7)
does the campaign's curated evidence get copied from this root into
`docs/qa_evidence/storefront_design_engine/phase5/w4_certification/`.

**Matrix path:** `{CAMPAIGN_REPORT_ROOT}/matrix.json` — exactly one file
for the whole campaign, read-merged-written atomically by every invocation
(§3.2's `_merge_into_matrix_json`/`_merge_theme_into_matrix_json`).

**Unique per-invocation result and log paths (never reused across
invocations — repairs the Round 2 draft's collision-prone
`w4c-theme-result-<key>.json` name, which could not distinguish two
different occasion/intensity/viewport cells for the same key):**

```
Base result:   {CAMPAIGN_REPORT_ROOT}/w4c-results/base/<key>.json
Base log:      {CAMPAIGN_REPORT_ROOT}/logs/base/<key>.log
Theme result:  {CAMPAIGN_REPORT_ROOT}/w4c-results/theme/<key>__<occasion>__<intensity>__<viewport>.json
Theme log:     {CAMPAIGN_REPORT_ROOT}/logs/theme/<key>__<occasion>__<intensity>__<viewport>.log
```

`_run_logged()`'s existing implementation opens its supplied log path with
mode `"w"` (truncate-on-open) — reusing one `browser.log` path across 154
invocations would silently overwrite 153 of them. Because every invocation
above is given a distinct, deterministic path, `_run_logged`'s existing
open-mode is safe to reuse completely unchanged; no modification to
`_run_logged` itself is needed or proposed.

**Matrix schema guard (`_validate_or_init_campaign_matrix`):**

```python
def _validate_or_init_campaign_matrix(self, matrix_path):
    if not matrix_path.exists():
        matrix_path.write_text(json.dumps({
            "_meta": {
                "schema_version": "w4c-matrix-v1",
                "certified_base_sha": "3a4fe9070584655548bae5a9bb574f3415bbf580",
                "total_cells_expected": 704,
            },
            "templates": {},
        }, indent=2), encoding="utf-8")
        return
    existing = json.loads(matrix_path.read_text())
    meta = existing.get("_meta", {})
    if meta.get("schema_version") != "w4c-matrix-v1" or meta.get("certified_base_sha") != "3a4fe9070584655548bae5a9bb574f3415bbf580":
        raise CommandError(
            f"W4C: {matrix_path} belongs to a different campaign/schema "
            f"({meta.get('schema_version')!r}/{meta.get('certified_base_sha')!r}) -- "
            "use a different --report-dir to start a new campaign; never silently merge across roots"
        )
```

Called once at the start of every `--w4c-all50` invocation (§3.2), before
any base or Theme cell runs. A batch launched against
`CAMPAIGN_REPORT_ROOT` that already holds a DIFFERENT campaign's
`matrix.json` (different `certified_base_sha` or `schema_version`) fails
fast with a `CommandError` — it never silently merges. Starting a genuinely
new campaign means passing a different, empty `--report-dir`.

### 3.10 Python wrapper final-status branching (new — Round 3, Important 2C)

The existing, unmodified, non-W4C path in `handle()` reads
`report_dir / "r4-browser-result.json"` and raises `CommandError` if either
the node exit code is nonzero or `summary.failed` is nonzero (harness
inventory §10.B) — this logic is untouched and still runs exactly as today
whenever `--w4c-all50` is absent.

When `--w4c-all50` IS passed, `handle()` takes a completely separate status
path that never reads or references `r4-browser-result.json` at all (that
file is not even written by the base/Theme node invocations, §3.7):

```python
if options["w4c_all50"]:
    # ... run the full base + Theme loop from section 3.2 ...
    aggregate = self._run_final_w4c_aggregator(matrix_path)   # section 15
    if aggregate["total_cells_recorded"] != 704 or aggregate["missing_cells"] or aggregate["duplicate_cells"]:
        raise CommandError(f"W4C: INCOMPLETE -- {aggregate}")
    if aggregate["fail_count"] > 0 or aggregate["blocked_count"] > 0:
        raise CommandError(f"W4C: certification did not pass -- {aggregate['fail_count']} FAIL, {aggregate['blocked_count']} BLOCKED")
    self.stdout.write(self.style.SUCCESS("W4C: 704/704 cells recorded, 0 FAIL, 0 BLOCKED -- PASS"))
else:
    # ... existing, completely unchanged non-W4C path, still reads r4-browser-result.json ...
```

W4C reports PASS ONLY from the 704-cell matrix aggregator (§15) — never
from the legacy result file. Every base/Theme node invocation's own nonzero
exit code is still recorded (against its exact cell/batch, inside that
cell's own result JSON, per §3.7's `process.exitCode` logic) but does not
by itself halt the campaign (§3.2's Important-2C exception) — only a
`_theme_cleanup_and_verify` failure does. After the outer command's
`finally` block, the existing SQLite backup/restore lifecycle still runs
exactly as it does today, in both the W4C and non-W4C paths, unchanged.

---

## 4. Pass/fail contract — Home

For every Template x viewport:

- [ ] HTTP 200 on the Store's public root.
- [ ] `<html dir="rtl">`.
- [ ] No horizontal overflow (`document.documentElement.scrollWidth <=
  document.documentElement.clientWidth + 2`).
- [ ] Exactly one `<header>` element (source-confirmed: every public-path
  header variant renders through `page_shell_header.html` or a
  `global_header/*` variant that itself emits exactly one `<header>`; the
  only other `<header>` tags in the template tree are confined to
  `dashboard/` admin templates, never reached by `home_visual.html`).
- [ ] Hero contract is data-driven (§6): for a Template whose canonical Home
  composition includes a `hero` token, Hero must render visibly and
  healthily (at least one visible media/copy element, no console/JS error);
  for a Template whose composition intentionally omits `hero`, the result is
  `N/A / expected absent`, never `FAIL`.
- [ ] Home composition rendered: `.wrap.sfb-preview-sections .rsec` count ==
  `len(preset.pages["home"])` (the exact registry-known composition length —
  same technique as W4B's `browser_qa_responsive_repair` script).
- [ ] Product Cards present and healthy: at least one `article.pcard` (or the
  Template's declared `card` variant's own real card selector) present
  wherever the Home composition includes a product-bearing section
  (`product_grid`/`product_rail`/`bento_products`/`featured_products`/etc.),
  each card resolving a real `href` (never `#`).
- [ ] Exactly one `<footer>` element (same source-confirmed reasoning as
  Header).
- [ ] Bottom Navigation follows the canonical responsive contract: `.gmn`
  (or the Template's declared `bottom_nav` variant class) computes
  `display:none` at Desktop/Tablet and a non-`none` display at Mobile — the
  exact `@media(max-width:680px)` breakpoint already in
  `storefront_builder.css`, never a new breakpoint.
- [ ] No duplicate shell: header/footer/bottom-nav counts above are exactly
  1/1/(0 or 1), never more.
- [ ] No duplicate functional sections: for every section family present in
  the Template's composition more than once by design (e.g. `harbor_imports`'
  two `product_section` rows — a pre-existing, approved duplication, not a
  W4C regression), the count matches the registry-declared composition
  exactly; any COUNT MISMATCH against the registry is a FAIL.
- [ ] No placeholder primary `href="#"` anywhere in the rendered Home page.
- [ ] Zero new console errors (compared against the certified W4B baseline
  console-error set for that Template, §12 — a pre-existing, already-known
  console warning is not a new W4C failure).
- [ ] Zero page (JS) errors.
- [ ] Zero unexpected failed requests (favicon 404s and the pre-existing
  "expected preview abort" pattern already excluded by the existing harness
  are excluded here too, never a new exclusion invented ad hoc).
- [ ] Accessibility-critical controls (§10) pass for every control actually
  present on Home for this Template.
- [ ] Session used: fresh, cookie-less anonymous `browser.newContext()` (§5)
  — Home is public customer traffic, never staff-cookied.

---

## 5. State isolation contract (repaired — Important 2 + 3, Round 2)

**Repair note:** the Round 1 version of this contract cookied Home/Listing
cells with the staff `manifest.session` cookie (mirroring the R4 harness's
phase3 blocks). The Independent Architect rejected this (Round 2, Important
2): W4C certifies CUSTOMER-FACING public traffic, so all four page classes —
Home, Listing, PDP, and Cart alike — must be genuinely anonymous. The staff
session is not carried into any public certification context at all; it is
not needed there, since every Store-state transition (apply/publish/Theme)
is a Python ORM/service call, never a browser action (§3.1).

### 5.1 Browser session isolation — all cells anonymous

Every one of the 600 base cells (Home, Listing, PDP, and Cart alike) and
every one of the 104 Theme cells uses its own fresh, **cookie-less**
`browser.newContext()` — no `manifest.session` field exists in W4C mode's
manifest at all, and no cell of any page class is ever cookied with a staff
session. Concretely:

- **Home / Listing cells (read-only):** fresh, cookie-less
  `browser.newContext()` per cell. Django's session middleware issues an
  anonymous session on first request exactly as it would for a real
  customer; no mutation occurs, so this session's lifetime is irrelevant
  beyond the cell itself.
- **PDP / Cart cells (mutating):** fresh, cookie-less `browser.newContext()`
  per cell (same mechanism as Home/Listing — the distinction that mattered
  in the Round 1 draft, cookied-vs-anonymous, no longer exists; ALL cells
  are anonymous now). Django's session middleware issues a brand-new session
  (and therefore an empty cart) on that context's first request — this is
  the mechanism that guarantees "start empty" without any direct DB/session
  manipulation, per the repair directive's explicit prohibition. Each Cart
  cell independently: starts empty (fresh context), adds exactly the
  deterministic fixture product via `context.request.post` to `cart:add`,
  exercises its bounded mutations (`cart:item-update`, `cart:item-remove`),
  reads the resulting DOM/totals via `page.goto('cart:detail')` in the SAME
  context, then the context is closed at the end of the cell — never reused
  for a later cell.
- PDP Add-to-Cart in one cell therefore cannot populate a later Cart cell:
  they never share a context, and a cookie-less context never resumes a
  prior session.
- Theme public-verification cells (104/104) are equally anonymous: the
  Theme MUTATION (apply/clear) is a Python-side Draft+publish operation
  (§3.6); the Theme's rendered effect is then OBSERVED via an anonymous
  browser navigation to the public Home page, exactly like any other Home
  cell.
- The staff session (`Client().force_login`) remains available ONLY for
  legacy R4 QA's own existing scenarios (used exactly as today, never
  changed) — it is never constructed, never present in, and never passed to
  a W4C manifest, since W4C's Python orchestrator needs no authenticated
  browser/HTTP path at all (every mutation goes through direct service
  calls, §3.1, §3.4, §3.6).

### 5.2 Template / Store state — real published-state verification

- Before each Template's 12 base cells (4 page classes x 3 viewports):
  Python calls `_apply_and_verify_published(store, preset)` (§3.4), which
  verifies the REAL `StorefrontLayout.published_version.template_provenance`
  — never `lpr.get_layout_preset(key).version` alone, which only proves the
  registry definition exists, not that it is published on the Store
  (harness inventory §11.1). This call is idempotent
  (`apply_preset_with_checkpoint`'s own `_draft_already_matches_preset`
  no-op check) — re-verifying an already-correct Template is cheap.
- Before every Theme cell and before every BASE-matrix batch: Python
  verifies the Store's published Theme selection via
  `load_store_appearance_manifest(layout.published_version).selections["theme"] == "theme.none.v1"`
  (harness inventory §11.4). If it is not (e.g. a prior interrupted Theme
  cell left it non-none), Python runs `_theme_cleanup_and_verify` (§3.6)
  before proceeding, and records this as a recovered-state event in
  `matrix.json`'s `_meta`.
- The Store's published Template MAY persist across a Template's own 12 base
  cells (no per-cell re-apply needed once verified) — only the BROWSER
  SESSION must not persist (§5.1).

### 5.3 Theme cleanup must survive failures (repaired — Python-owned, per §3.1/§3.2/§3.6)

**Repair note (Round 1→3):** the Round 1 draft described this lifecycle
without naming which process runs it; Round 2 then incorrectly implied a JS
`try/finally` inside `run.mjs`. Per §3.1's division of authority, every
Store-state transition — including Theme apply/clear/publish/verify — is
Python's responsibility; Node only observes the rendered result. The
Round-3-corrected, single source of truth for this lifecycle is
`_run_one_theme_cell` in §3.2 (its own `try/finally`, running once per
Theme cell — 104 separate calls total, never folded into a base
invocation, per Important 1's cardinality fix) plus `_theme_cleanup_and_verify`
in §3.6 (the `finally` body, with the corrected `pv is None`-first ordering).
This subsection is intentionally no longer a second description of that
pseudocode — see §3.2/§3.6 for the exact, current code.

Binding invariants (restated, not redefined): if `_theme_cleanup_and_verify`
itself raises, the ENTIRE `--w4c-all50` run halts immediately (no further
base or Theme cells execute, §3.2's Important-2C exception), the run is
reported `BLOCKED`, and a manual/automated Store-state repair +
re-verification is required before any further certification proceeds
(§3.6). A Theme assertion/navigation failure inside the `try` block is
recorded as a FAIL for that one cell but does NOT skip the `finally` —
cleanup always runs regardless of the `try` block's outcome. No direct
writes to a published version at any point — every Theme mutation goes
through `get_or_create_draft` + the canonical mutation
(`apply_theme`/`clear_theme`) + `publish`, exactly as `layout_service` and
`appearance_authority_service` already define them (harness inventory
§11.4) — Node never calls into Django, and Python never reaches into the
browser.

---

## 6. Hero contract (new — data-driven, not key-special-cased)

Derived from source, not guessed: `_RecipeSpec.hero == "none"` for exactly 5
of the 50 Templates — `premium_leather`, `utility_catalog`, `tool_finder`,
`collection_index`, `mother_utility` (verified programmatically against
`_SPECS`; cross-checked against each of these 5 Templates' compiled Home
composition tuple, none of which contains a `hero` token — the two signals
agree for all 5, confirming `hero == "none"` is a reliable, render-facing
proxy).

- [ ] For the 45 Templates with a declared Hero: the Home contract's Hero
  check (§4) is `PASS`/`FAIL` based on real rendered health.
- [ ] For the 5 Templates listed above: the Home contract's Hero check
  result is `N/A` (recorded explicitly in `matrix.json`, never silently
  omitted, never coerced to `PASS`), and is excluded from any FAIL-counting
  logic for that field.
- [ ] No Template key is special-cased in browser code — the check queries
  the live `LayoutPresetDefinition.pages["home"]` section-key sequence for
  presence/absence of `"hero"` at execution time, deriving the expectation
  from data, not from a hardcoded key list (the 5-key list above is the
  CURRENT observed result of that data-driven query, recorded here for
  planning traceability, not the mechanism itself).

---

## 7. Pass/fail contract — Listing

Route: `catalog:product-list` (`/products/`). For every Template x viewport:

- [ ] HTTP 200.
- [ ] Header/Footer/Bottom-Nav contract identical to §4 (reused, not
  redefined).
- [ ] `dir="rtl"`, no horizontal overflow.
- [ ] Product cards rendered via the Template's declared `card` variant
  (same `article.pcard`/`a.pcard-hitarea` canonical markers
  `product_card.html` already emits for every card style).
- [ ] Search/filter/sort/pagination controls present and usable where the
  Listing page renders them (reusing the exact `<nav>`-labelled pagination
  and `form[role=search]` contract already proven by
  `public_task7_qa.mjs` — never a new selector).
- [ ] Real product links (first product card's `href` resolves, HTTP 200,
  verified via an in-page `fetch()` from the SAME anonymous context —
  Listing is a read-only, cookie-less cell like every other page class, §5).
- [ ] No dead interaction (no `href="#"`, no disabled-looking control that
  is actually meant to be active).
- [ ] Accessibility-critical controls (§10) for filter/sort/pagination.
- [ ] Zero new console/page/request errors.

---

## 8. Pass/fail contract — PDP

Route: `catalog:product-detail` for the deterministic fixture product (§2).
Read-mostly (variant/quantity interaction is client-side; only Add-to-Cart
mutates), so PDP cells use the cookie-less fresh-context pattern (§5.1) for
consistency with the Cart cells that follow from them within the same cell's
Add-to-Cart check. For every Template x viewport:

- [ ] HTTP 200.
- [ ] Header/Footer/Bottom-Nav contract identical to §4.
- [ ] `dir="rtl"`, no horizontal overflow.
- [ ] Product gallery renders at least one image element.
- [ ] Price displayed.
- [ ] Stock/availability state displayed (in-stock, since the fixture
  product is in stock — an out-of-stock cell is out of this matrix's scope,
  covered instead by existing unit/contract tests).
- [ ] Variant controls present and change the displayed price/availability
  when a different Size/Color option is selected (the fixture product is
  guaranteed variant-bearing, §2).
- [ ] Quantity control present and adjustable.
- [ ] Add-to-Cart path: submitting the canonical `hx-post="/cart/add/..."`
  form succeeds (cart count increments) — the exact form
  `public_task8_qa.mjs` already proved is the single shared form for both
  the in-flow CTA and the mobile Sticky-Add-to-Cart bar. This mutation uses
  the cell's own fresh, cookie-less context (§5.1) and is discarded with it.
- [ ] Mobile Sticky-Add-to-Cart bar present at Mobile viewport where the
  Template's `bottom_nav`/shell declares it (reusing `public_task8_qa.mjs`'s
  own hidden-on-desktop/visible-on-mobile/no-content-obscuration checks,
  never re-invented).
- [ ] Product Detail Tabs (Desktop, ARIA `role=tab`/`tabpanel`) or Accordion
  (Mobile, DOM source-order) contract — reusing `public_task5_qa.mjs`'s
  existing checks verbatim.
- [ ] Real navigation: at least one in-page link (e.g. back to Listing or a
  related-category link if present) resolves HTTP 200.
- [ ] Accessibility-critical controls (§10) for variant/quantity/Add-to-Cart.
- [ ] Zero new console/page/request errors.

---

## 9. Pass/fail contract — Cart

Route: `cart:detail`, after one canonical `cart:add` of the fixture product,
in a fresh, cookie-less context per cell (§5.1). For every Template x
viewport:

- [ ] HTTP 200.
- [ ] Header/Footer/Bottom-Nav contract identical to §4.
- [ ] `dir="rtl"`, no horizontal overflow.
- [ ] Cart item(s) rendered (the fixture product's line item visible).
- [ ] Quantity control present; incrementing via `cart:item-update` reflects
  in the displayed line total and cart total (no duplicated commerce math —
  the displayed total matches `apps/cart/services/pricing.py`'s own
  computed total, read from the same context the template renders, never a
  second client-side recomputation).
- [ ] Remove mechanic (`cart:item-remove`) present and functional.
- [ ] Totals displayed.
- [ ] Checkout CTA present.
- [ ] Free-Shipping Goal widget (from W1) rendered in its below-threshold or
  above-threshold state consistent with the fixture product's price vs. the
  Store's configured threshold — reusing `public_w1_qa.mjs`'s own
  progress-bar-bounded-width/RTL/overflow checks, never re-invented. The
  all-digital and empty-cart states are out of scope for this per-Template
  matrix (already certified once, fixture-independently, by W1 — see harness
  inventory §6).
- [ ] Accessibility-critical controls (§10) for quantity/remove/checkout.
- [ ] Zero new console/page/request errors.
- [ ] Cell teardown: the context is closed at the end of this cell,
  discarding its session/cart — never reused, never explicitly "cleared" via
  DB/session manipulation (§5.1).

---

## 10. Accessibility-critical contract (bounded, technical — not a WCAG audit)

Only the controls actually exercised above are checked; nothing broader is
claimed. For each control below, present-and-exercised implies these checks
run; absent-for-this-Template implies the check is skipped (recorded as
`n/a`, never silently passed):

- [ ] Mobile navigation opener/closer: accessible name, `aria-expanded`
  state toggles, keyboard-focusable, Escape closes (reusing
  `public_task5_qa.mjs`'s Drawer focus-trap/return contract).
- [ ] Search control: `form[role=search]`, `input[name=q]` accessible name
  (reusing `public_task7_qa.mjs`).
- [ ] Product Card primary link / Quick View trigger: accessible name,
  keyboard-focusable (reusing `public_task5_qa.mjs`'s Quick-View focus
  containment/return contract where the Template's card style exposes one).
- [ ] PDP variant and quantity controls: accessible name, semantic
  `<select>`/`<input type=number>` or ARIA-equivalent, keyboard-operable.
- [ ] Add-to-Cart: accessible name, disabled state exposed via
  `aria-disabled`/`disabled` (never a purely visual-only disabled state) for
  out-of-stock (verified once against a deliberately out-of-stock fixture
  product, not per-Template).
- [ ] Cart quantity/remove/checkout controls: accessible name,
  keyboard-operable.
- [ ] Theme controls: not exercised (Theme's own R4 controls are an
  admin-editor concern, not exposed on the public certification path — this
  contract explicitly does not claim public-path Theme accessibility beyond
  what §1's Theme matrix already checks structurally).

---

## 11. Visual distinctness contract (repaired — uses Desktop AND Mobile)

Structural uniqueness (W4B's `recipe_signature()`/diversity contract) and
rendered visual certification are separate gates; both are required, and a
passing structural signature never substitutes for a rendered check here.

- [ ] Build one **rendered-identity matrix**: for all 50 Templates, tabulate
  (from real Home captures at BOTH Desktop and Mobile — repaired per
  Important 4, since Bottom Navigation is a mobile-only visual and cannot be
  certified from Desktop evidence alone) the actually-rendered Header
  family, Hero family (or intentional Hero absence, §6), layout/composition
  shape, Product Card style, density, typography, Footer family, and
  Bottom-Nav style.
- [ ] Cluster the 50 by this rendered-identity matrix. Any cluster of 2+
  Templates whose rendered identity differs ONLY by palette/font/radius
  (never by Header/Hero-or-absence/layout/Product-Card/density/typography/
  Footer/Bottom-Nav) is flagged `NEEDS REPAIR` — palette-only difference is
  explicitly insufficient per the plan's own text.
- [ ] Any `NEEDS REPAIR` finding STOPS the certification run for that pair/
  cluster and is returned for a separate, reviewed repair round before
  certification can close — it is never silently passed because
  `recipe_signature()` was already unique (W4B's structural test does not
  inspect rendered output).
- [ ] The rendered-identity matrix and cluster findings are published as
  `visual_distinctness_matrix.json` + a human-readable
  `visual_distinctness_matrix.md` (§12), both explicitly citing which
  viewport (Desktop or Mobile) evidenced each axis — Bottom-Nav rows always
  cite Mobile.

---

## 12. Evidence-volume contract (repaired — Important 4)

Canonical evidence root: `docs/qa_evidence/storefront_design_engine/phase5/w4_certification/`.

Required artifacts:

1. `matrix.json` — one machine-readable file covering every one of the 704
   certification cells (§1), schema in §13.
2. `home_gallery/` — **100 files** (repaired from 50): for each of the 50
   Templates, one Home Desktop screenshot (`<key>_home_desktop.jpg`, 1440×900)
   AND one Home Mobile screenshot (`<key>_home_mobile.jpg`, 390×844) — mandatory,
   for W5 review, which explicitly requires Desktop + Mobile inspection
   including the Bottom Navigation axis. Sourced DIRECTLY from that
   Template's own `--w4c-all50` base certification Home cells (§3.2/§3.7),
   which already run at exactly these two viewports — never from
   `capture_ready_template_previews.py`'s `--full-qa` mode, whose own
   canonical Home-Desktop viewport is a confirmed, different 1440×1100
   (harness inventory §11.6), not a substitutable capture. Home Tablet is
   exercised in `matrix.json` but not gallery-retained.

   **Two-stage contract (repaired — Round 4, Important 2):** during the
   live campaign, each base invocation writes its two Home screenshots to a
   STAGING path under the external campaign root —
   `{CAMPAIGN_REPORT_ROOT}/screenshots/home/<key>_home_desktop.jpg` /
   `..._home_mobile.jpg` — referenced by that Template's own
   `w4c-results/base/<key>.json`. No campaign-in-progress screenshot is ever
   written directly into the Git repository. AFTER the campaign completes
   (§15's aggregator reports `total_cells_recorded == 704`,
   `missing_cells == []`, `duplicate_cells == []`), Task 6 (§17) copies
   exactly those 100 staged files — one Desktop + one Mobile per Template,
   read from each Template's own base result JSON, never re-captured — into
   `docs/qa_evidence/storefront_design_engine/phase5/w4_certification/home_gallery/`
   as the final, committed evidence. A final evidence gate (Task 6) then
   verifies: `home_gallery/` file count `== 100`; all 50 keys have both a
   Desktop and a Mobile file; and every final file traces back to a cell
   whose `matrix.json` entry recorded `result: "PASS"` for that Template's
   Home/desktop or Home/mobile cell (a staged screenshot from a FAILing Home
   cell is never promoted into the gallery silently — a FAIL there is
   itself a certification blocker handled by §4/§11, not hidden by omission
   from the gallery).
3. `gallery_index.md` — a single 100-row-referencing, 50-Template index
   (key, label_fa, Desktop thumbnail reference, Mobile thumbnail reference,
   rendered-identity summary including Bottom-Nav style) suitable for
   Product Owner/W5 review — no separate per-Template markdown files.
4. `representative_screenshots/` — one Desktop screenshot per Template for
   Listing, PDP, and Cart (50 x 3 = 150 files) for the passing, non-Home page
   classes; Tablet/Mobile screenshots for these page classes are NOT
   committed when `matrix.json` already proves the result — Tablet/Mobile
   checks still run and are still recorded in `matrix.json`, only their
   screenshots are not retained on success.
5. `failures/` — a screenshot for every FAILING non-Home cell, at the exact
   viewport that failed, named `<key>_<page_class>_<viewport>_FAIL.jpg`. Home
   failures reuse the mandatory `home_gallery/` assets (already committed,
   both Desktop and Mobile) and need no separate failure screenshot.
6. `theme_qa/` — Tier 1 failure-only screenshots (one per failing cell, of
   50) plus all Tier-2 cells retained in full (27 x 2 = 54, since Tier 2 is
   the small, deliberately deep sample).
7. `visual_distinctness_matrix.json` + `.md` (§11), citing Desktop and
   Mobile evidence explicitly.
8. `failure_summary.md` — every FAIL/BLOCKED cell across all 704, one row
   each, with the exact reason.
9. `browser_error_summary.md` — aggregated console/page/failed-request
   findings across the whole run, cross-referenced against the certified
   W4B/pre-existing baseline (§14) so only genuinely new errors are flagged.
10. `architecture_duplication_audit.md` — confirms zero new renderer/
    registry/section-type/Theme-mechanism/tenant-resolver/ProductCard-path/
    cart-path/Bottom-Nav-system/search-backend/parallel harness was
    introduced by the bounded extension (§3), and explicitly confirms
    `apps/storefront_builder/static/ready_template_previews/**` was touched
    only by the deliberate Gallery-refresh step (§3.3/§16), never by the
    `--w4c-all50` run itself.
11. `execution_report.md` — narrative tying together all of the above,
    modeled on W4B's own `10_implementation_report.md`.

Never committed: a screenshot for every passing Tablet/Mobile
Listing/PDP/Cart cell (proven instead by `matrix.json`).

---

## 13. Machine-readable matrix schema

Directly descended from W4B's `browser_qa_responsive_repair/summary.json`
shape (harness inventory §1.6), extended with a `page_class` dimension:

```json
{
  "key": "cedar_home",
  "version": "2",
  "page_classes": {
    "home": {
      "desktop": { "...": "see section 4 fields, plus hero_expected: true/false and hero_result: PASS/FAIL/N-A" },
      "tablet": { "...": "see section 4 fields" },
      "mobile": { "...": "see section 4 fields" }
    },
    "listing": { "desktop": {}, "tablet": {}, "mobile": {} },
    "pdp": { "desktop": {}, "tablet": {}, "mobile": {} },
    "cart": { "desktop": {}, "tablet": {}, "mobile": {} }
  },
  "theme": {
    "tier1_cell": { "occasion": "muharram", "intensity": "balanced", "result": "PASS", "cleanup_verified": true },
    "tier2": null
  }
}
```

Each per-viewport object carries, at minimum: `http_status`, `rtl`,
`overflow`, `header_count`, `footer_count`, `bottom_nav_present`,
`bottom_nav_display`, `rsec_count`, `expected_rsec_count`,
`product_cards_present`, `dead_href_count`, `console_errors` (list),
`page_errors` (list), `failed_requests` (list), `accessibility_checks`
(object, per §10), `result` (`"PASS"`/`"FAIL"`/`"BLOCKED"`/`"N/A"`), `reason`
(string, required when `result` is not `PASS`), `screenshot` (path or `null`
when not retained per §12). A `session_mode` field is deliberately NOT
present — every cell of every page class is anonymous (§5), so the field
would carry no information.

A top-level `_meta` object records: `run_started_at`, `run_finished_at`,
`certified_base_sha`, `w4c_branch_head_sha`, `total_cells_expected` (704),
`total_cells_recorded`, `missing_cells` (list — must be empty for a valid
PASS report), `duplicate_cells` (list — must be empty), `recovered_state_events`
(list — any time §5.2's pre-batch Theme/Template verification found and
repaired unexpected state).

---

## 14. Regression / baseline comparison strategy

- [ ] Run `python manage.py check --settings=shop_core.settings` — expect
  clean.
- [ ] Run `python manage.py makemigrations --check --dry-run
  --settings=shop_core.settings` — expect "No changes detected". If W4C's
  bounded harness extension requires any production code or migration beyond
  the two files listed in §3, STOP for Architect review before proceeding —
  this workstream is QA/evidence, not a production-behavior change.
- [ ] Run `git diff --check` — expect clean.
- [ ] Re-run `apps.storefront_builder.tests` in full and compare failure/
  error identities against the certified W4B evidence
  (`docs/qa_evidence/storefront_design_engine/phase5/w4b_template_curation/implementation/09_full_suite_exact_head_base_comparison.md`
  and `05_full_storefront_builder_exact_head.txt` — 3235 tests / 30 failures
  / 2 errors / 4 skipped, W4B-only failures/errors = 0). Historical baseline
  failures are never automatically treated as W4C regressions; only a
  genuinely NEW failure/error identity, or a CHANGED reason for an existing
  one, counts as a W4C regression. Extending `qa_storefront_builder_r4.py` /
  `run.mjs` behind a new, default-off flag is not expected to change any
  existing test's identity or reason — this must still be verified, not
  assumed.
- [ ] Existing `test_ready_template_real_previews.py` must remain green
  unchanged (proves `capture_ready_template_previews.py`'s pre-existing
  behavior is untouched, §3.3).
- [ ] Existing R4 QA scenarios 01–15 and the phase3/showcase blocks must
  remain behaviorally identical when `--w4c-all50` is NOT passed (the new
  flag defaults to off; this is itself asserted by RED case 8, §17 Task 1).
- [ ] Expected migrations for this entire workstream: **0**.

---

## 15. Execution / resumability plan (repaired — 704 cells / 154 invocations, state-aware resume, one campaign root)

The 704-cell, 154-invocation campaign (§3.2: 50 base invocations × 12 cells
+ 104 Theme invocations × 1 cell) is chunked internally by Template/Theme-cell
batch (implementation detail only — never a parallel Phase-5 workstream,
never a second harness invocation path):

- [ ] `--w4c-all50` accepts an additional `--only <key1,key2,...>` sibling
  flag (mirroring `capture_ready_template_previews.py`'s existing `--only`,
  extended to a comma-separated list) to run a subset of Templates' base
  AND Theme cells per invocation.
- [ ] Every invocation in one campaign passes the SAME explicit
  `--report-dir /var/tmp/rastisi_w4c_campaign` (§3.9) — there is no
  timestamp-based default for W4C mode; omitting `--report-dir` under
  `--w4c-all50` is itself a `CommandError` (never silently falls back to a
  fresh, unshared directory).
- [ ] Each invocation appends its results into the SAME `matrix.json` at
  that one campaign root (never overwrites it wholesale) — implemented as:
  `_validate_or_init_campaign_matrix` (§3.9) guards against a mismatched
  prior campaign, then `_merge_into_matrix_json`/`_merge_theme_into_matrix_json`
  read the existing file, merge new/updated per-key (or per-key+occasion+
  intensity+viewport) entries, and write back atomically (write to a temp
  file, then rename) so a crash mid-run cannot corrupt previously-recorded
  results.
- [ ] Ordering is stable and deterministic: Templates are processed in
  `_SPECS` source order for the base loop, then Tier-1 Theme cells in the
  same order, then Tier-2's 54 cells in their own fixed
  Template×occasion×intensity×viewport nesting order (§3.2) — never
  randomized, so re-running an interrupted batch resumes at a predictable
  point.
- [ ] Every cell records the exact Template `key` + `version` and the exact
  `page_class`/`viewport` (base) or `occasion`/`intensity`/`viewport`
  (Theme) — no implicit/positional cell identity, and every cell's result
  file lives at its own unique, deterministic path (§3.9) — never a shared
  or reused filename.
- [ ] A FAILing cell does not erase or roll back any other already-recorded
  cell (per-key, per-page-class, per-viewport entries are independent
  dictionary keys in the JSON structure, never a flat ever-growing list that
  could be corrupted by a partial write) — per §3.2's Important-2C
  exception, an ordinary FAIL does not even stop the campaign; it is simply
  recorded and the loop continues to the next cell/invocation.
- [ ] **Resume state verification:** before continuing an interrupted
  campaign, the resuming invocation does NOT assume the previous batch left
  Store state clean. It explicitly re-verifies: (a) the published Template
  identity for the NEXT key to be processed (§3.4's
  `_apply_and_verify_published` — re-applies if drifted), and (b) the
  published Theme identity is `theme.none.v1` (§3.6's `_verify_theme_is_none`
  — runs `_theme_cleanup_and_verify` if not, before any further base or
  Theme cells run). Both checks are recorded in `matrix.json`'s
  `_meta.recovered_state_events` when they find and fix drift. Resume never
  overwrites an already-`PASS` cell's entry unless explicitly running a
  separately-documented recheck mode (not part of this plan's default
  execution path).
- [ ] A final aggregator step (`_run_final_w4c_aggregator`, §3.10 — run
  after all batches, and internally at the end of every single-invocation
  full run too) reads `matrix.json` and verifies: `total_cells_recorded ==
  704`, `missing_cells == []`, `duplicate_cells == []`, `fail_count == 0`,
  `blocked_count == 0`. A partially-completed run is reported as
  `INCOMPLETE`, never as `PASS` — this aggregator check is itself part of
  `execution_report.md` (§12).
- [ ] No parallel Phase-5 workstream is started to speed this up; internal
  batching is the only concurrency this plan allows.

---

## 16. Architecture constraints (restated, binding)

- [ ] No new renderer, Ready Template registry, version registry, section
  type, Store-Appearance family, Theme mechanism, tenant resolver,
  ProductCard path, cart/add-to-cart path, Bottom Navigation system,
  search backend, or browser-rendering/QA authority is introduced.
- [ ] The only files changed for the harness extension are
  `tools/storefront_builder_r4_qa/run.mjs` and
  `apps/storefront_builder/management/commands/qa_storefront_builder_r4.py`.
- [ ] `capture_ready_template_previews.py` is not modified and is never the
  source of the mandatory W5 Home gallery (that comes directly from the
  `--w4c-all50` certification cells themselves, §12/Task 6). It is only
  invoked, unmodified, in its existing `--only <key>` mode, for the
  DIFFERENT, pre-existing responsibility of refreshing a static Gallery
  preview asset — and only for a key found genuinely stale by the existing
  fingerprint contract (§12/Task 6/harness inventory §11.6), never blindly
  for all 50 — recorded in `execution_report.md` as a deliberate, separate
  refresh, distinct from and never triggered by the `--w4c-all50` run
  itself.
- [ ] No new Node package is added — the extension reuses the
  `playwright-core` dependency `run.mjs` already borrows via `createRequire`
  from `tools/storefront_builder_qa/package.json`.
- [ ] Zero migrations.
- [ ] No merchant IDs or per-Template fake business data enter any
  `_RecipeSpec` or fixture.
- [ ] One PR, unmerged, base `feature/phase5-design-expansion`, head
  `feature/phase5-w4c-all50-certification`, Architect review, Product Owner
  approval, only then merge — identical lifecycle to W4A/W4B.

---

## 17. Task checklist (for the authorized implementation round — not this round)

- [ ] **Task 1 — RED contract tests asserting the DESIRED W4C behavior**
  (repaired — Round 1 Important 5B + Round 2 §5: exact module, exact 16
  cases, exact commands; these assert the feature that should exist and
  currently fails because it does not, never "absence of a feature"):

  **Exact test module:** `apps/storefront_builder/tests/test_w4c_all50_certification_harness.py`
  (new file — no existing module is a closer owner: `test_ready_template_real_previews.py`
  owns the unrelated Gallery-screenshot contract, and there is no existing
  R4-QA-wrapper test module to extend).

  RED cases (26 total — 16 from Round 2 §5, plus 10 added in Round 3 §4
  closing the execution-control-flow gaps):
  1. `add_arguments` accepts `--w4c-all50` (`action="store_true"`).
  2. `add_arguments` accepts `--only` as a comma-separated list, and this
     flag only affects Template selection when `--w4c-all50` is also passed
     (asserted via `Command().create_parser(...)` introspection, not a full
     run).
  3. Calling `handle()` with `--w4c-all50` calls
     `_prepare_w4c_certification_fixture` and never calls
     `_prepare_r4_sandbox` (mock/patch both methods and assert call counts).
  4. `_build_w4c_fixture(store)` returns a `templates` list of exactly 50
     `{key, version}` pairs, read live from `lpr.list_ready_templates()`
     (assert the returned list matches that live call's output, not a
     hardcoded literal).
  5. Published-Template verification reads
     `StorefrontLayout.objects.get(store=store).published_version.template_provenance["template"]`
     — not `lpr.get_layout_preset(key).version` alone (assert
     `_apply_and_verify_published` raises `CommandError` when
     `published_version` is `None`, even if the registry has the right
     version, proving the check is state-based not registry-based).
  6. `manifest["public_url"]` contains the customer-facing host
     (`shop-{store.admin_subdomain}.{RASTISI_ADMIN_DOMAIN_SUFFIX}`) when
     `w4c_all50=True` is passed to `_build_manifest`.
  7. `manifest["resolver_host"]` equals the exact same host as
     `manifest["public_url"]`'s host component (string-parsed comparison).
  8. Calling `_build_manifest(..., w4c_all50=False, showcase=False)` (the
     ordinary non-W4C path) produces byte-identical `origin`/`public_url`/
     `resolver_host` values to the certified pre-repair behavior
     (`http://127.0.0.1:{port}/`, `resolver_host=None`) — a regression guard,
     not new behavior; PASSES today and must keep passing.
  9. Every cell manifest passed to `run.mjs` in W4C mode has no `session`
     key at all (assert the per-Template active-key envelope dict has no
     `"session"` key, proving no staff cookie is ever threaded into a public
     certification context).
  10. The aggregator utility (introduced in Task 2) rejects a `matrix.json`
      with `total_cells_recorded != 704`.
  11. The aggregator rejects a `matrix.json` with a non-empty `missing_cells`
      list — reports `INCOMPLETE`, never `PASS`.
  12. The aggregator rejects a `matrix.json` with a non-empty
      `duplicate_cells` list.
  13. A Hero-`none` Template's (§6) Home cell computation returns
      `hero_result: "N/A"`, derived from the live
      `LayoutPresetDefinition.pages["home"]` section-key sequence lacking a
      `"hero"` token — never `"FAIL"`, and never keyed off a hardcoded
      Template-key list.
  14. `_build_w4c_fixture(store)["tier1_occasions"]` assigns exactly the
      deterministic cycle (§1.1) for all 50 keys in `_SPECS` order — assert
      the full 50-entry dict matches the exact table in §1.1, not merely its
      length or distribution.
  15. `_theme_cleanup_and_verify` raising an exception (simulated via a
      mocked `clear_theme` that leaves a non-`theme.none.v1` state) halts
      the per-Template loop immediately and marks the run `BLOCKED` — no
      further Template in the batch is processed after the raise.
  16. **(repaired — Round 4, Important 2)** every base result JSON
      (`{CAMPAIGN_REPORT_ROOT}/w4c-results/base/<key>.json`) records exactly
      one Home-Desktop and one Home-Mobile screenshot path, both under the
      CAMPAIGN root's staging tree
      (`{CAMPAIGN_REPORT_ROOT}/screenshots/home/<key>_home_desktop.jpg` /
      `..._home_mobile.jpg`, §12/§3.9) — never under the final repository
      evidence tree
      (`docs/qa_evidence/storefront_design_engine/phase5/w4_certification/home_gallery/`,
      which does not exist until Task 6 runs after the campaign completes)
      and never under `capture_ready_template_previews.py`'s output paths
      (`apps/storefront_builder/static/ready_template_previews/**`). This
      test asserts the STAGING path shape only; it never requires a
      repository evidence file to exist during a live campaign run.

  **Added in Repair Round 3** (§3.2/§3.6/§3.7/§3.9/§3.10 execution
  control-flow closure):

  17. A full base-batch run against a fixture of N Templates produces
      exactly N planned base `run.mjs` invocations, and each one's recorded
      result covers exactly 12 cells (4 page classes × 3 viewports) — assert
      against a small N (e.g. `N=2`) rather than the full 50 to keep the
      test fast.
  18. A full Theme-batch run produces exactly 104 planned Theme `run.mjs`
      invocations (50 Tier-1 + 54 Tier-2) when run against the full
      50-Template fixture, each one's recorded result covering exactly 1
      cell — assert the exact count 104, not merely "more than one."
  19. For the full 50-Template fixture, total planned Node invocations
      (base + Theme) equals `50 + 104 = 154`, while
      `matrix.json._meta.total_cells_expected` remains `704` — the two
      numbers are asserted as deliberately different, proving Task 1
      Round-2's contradiction (one invocation folding both base and Theme
      cells together) cannot silently reappear.
  20. Neither `w4cBaseCertification` nor `w4cThemeCertification` calls
      `process.exit()` anywhere in their source (a static source-grep
      assertion against `run.mjs`, since a runtime `process.exit()` inside a
      spawned child process cannot be observed from the Python test
      process) — FAILS today because these functions do not exist.
  21. Passing `--store-slug`/`--username` WITHOUT `--w4c-all50` still reads
      and asserts against `r4-browser-result.json` exactly as today
      (mock `_run_logged` to return exit code 0 and a `summary.failed: 0`
      result file; assert `handle()` reads that exact file) — a regression
      guard, PASSES today and must keep passing.
  22. Passing `--w4c-all50` never opens or reads `r4-browser-result.json` at
      any point in `handle()` (assert via a filesystem-access spy/mock that
      no read of that exact filename occurs during a W4C run) — FAILS today
      only in the sense that the W4C code path itself doesn't exist yet to
      make this assertion meaningful; once Task 2 lands, this must hold.
  23. `--w4c-all50` reports overall PASS if and only if the final matrix
      aggregator (§15) reports `total_cells_recorded == 704`,
      `missing_cells == []`, `duplicate_cells == []`, `fail_count == 0`, AND
      `blocked_count == 0` — construct a `matrix.json` with `fail_count: 1`
      and assert `handle()` raises `CommandError`, never reports success.
  24. `_apply_and_verify_published` raises `CommandError` (never
      `AttributeError`) when `layout.published_version` is `None` — assert
      the exact exception type via `assertRaises(CommandError)`, not a bare
      `assertRaises(Exception)`, so a regression back to the unordered
      Round-2 check is caught precisely.
  25. Two `qa_storefront_builder_r4.py --w4c-all50` invocations against the
      SAME `--report-dir` merge into one `matrix.json` (assert the second
      invocation's `_validate_or_init_campaign_matrix` does not reinitialize
      the file, and that both invocations' per-key entries are both present
      afterward); an invocation against a `--report-dir` already holding a
      `matrix.json` with a different `certified_base_sha` raises
      `CommandError` and does NOT merge.
  26. For the same key, a base result path and a Theme result path (for
      three different occasion/intensity/viewport combinations) are all
      distinct file paths with no collisions — assert
      `_write_w4c_base_manifest`'s and `_write_w4c_theme_manifest`'s
      `result_path`/`log_path` values are pairwise unique across a
      representative set of calls.

  **Added in Repair Round 4** (§3.2 `--only`-must-filter-Tier-2 fix):

  27. A `selected_keys` subset excluding both `warm_boutique` and
      `beauty_dew` (e.g. `["editorial_jewelry"]`) produces zero Tier-2
      invocations and zero Tier-2 result files — assert the Tier-2 loop
      body is never entered for such a batch.
  28. `selected_keys = ["warm_boutique"]` alone produces exactly 27 Tier-2
      invocations (3 occasions × 3 intensities × 3 viewports), all for
      `warm_boutique`, and zero for `beauty_dew`.
  29. `selected_keys = ["beauty_dew"]` alone produces exactly 27 Tier-2
      invocations, all for `beauty_dew`, and zero for `warm_boutique`.
  30. The full 50-key fixture (`selected_keys` = all 50) still produces
      exactly 54 Tier-2 invocations total (27 + 27) — a regression guard
      proving the per-key filter does not accidentally under- or
      over-count when every key happens to be selected.
  31. Running batch A (`--only warm_boutique`, producing 27 Tier-2 result
      files) followed by batch B (`--only editorial_jewelry`, which does
      not touch Tier-2 at all) leaves all 27 of batch A's Tier-2 result
      files byte-identical (mtime and content) after batch B completes —
      proving an unrelated `--only` batch cannot rewrite Tier-2 evidence it
      never executed.

  29 of these 31 cases are feature-contract assertions and are expected RED
  (FAIL) on the current certified base (`3a4fe907...`), because the
  `--w4c-all50` mode, `_build_w4c_fixture`, `_apply_and_verify_published`,
  `_theme_cleanup_and_verify`, the Tier-2 filter, the aggregator, and the
  Hero/gallery-staging contracts do not exist yet. Cases 8 and 21 are
  deliberate exceptions: they are non-interference/regression guards
  asserting the EXISTING, unmodified non-W4C behavior, and are expected to
  PASS (GREEN) immediately, before any W4C code is written — this is not a
  contradiction of the RED state above; it is the explicit proof that the
  ordinary R4 QA path is architecturally independent of the new W4C code
  from the very first commit of this test file.

  **Exact focused test command:**
  ```
  python manage.py test apps.storefront_builder.tests.test_w4c_all50_certification_harness --settings=shop_core.settings
  ```
- [ ] Task 2 — Implement the bounded `--w4c-all50` extension across
  `qa_storefront_builder_r4.py` (`_prepare_w4c_certification_fixture` §3.3,
  `_build_w4c_fixture` §3.2, `_apply_and_verify_published` §3.4,
  `_verify_theme_is_none`/`_verify_published_theme`/`_theme_cleanup_and_verify`
  §3.6, the separate base-loop/`_run_one_theme_cell` Python control flow
  §3.2 invoking `run.mjs` 50+104=154 times, the 3-way `host` branch in
  `_build_manifest` §3.5, `_validate_or_init_campaign_matrix`/
  `_merge_into_matrix_json`/`_merge_theme_into_matrix_json` §3.9, the
  W4C-only final-status branch §3.10) and `run.mjs` (the `if (manifest.w4c)`
  top-level guard dispatching on `manifest.mode` and the new
  `w4cBaseCertification`/`w4cThemeCertification` functions — every cell of
  every page class anonymous per §5, structured `try/finally` cleanup with
  no `process.exit()`, per §3.7), and the small aggregator utility (§15/§17
  Task 1).
- [ ] Task 3 — Prove GREEN on Task 1's tests, plus existing
  `test_ready_template_real_previews.py` and the existing R4 QA scenario
  suite (both must remain green and behaviorally unchanged when
  `--w4c-all50` is absent). Exact commands:
  ```
  python manage.py test apps.storefront_builder.tests.test_w4c_all50_certification_harness --settings=shop_core.settings
  python manage.py test apps.storefront_builder.tests.test_ready_template_real_previews --settings=shop_core.settings
  python manage.py qa_storefront_builder_r4 --store-slug rasti-mode-demo --username w4c_qa_owner --port 8765 --browser-channel auto --settings=shop_core.settings
  ```
  (the third command is the existing, unmodified R4 QA gate invocation, run
  WITHOUT `--w4c-all50`, using the same `w4c_qa_owner` user §2 defines — to
  prove byte-for-byte non-interference.)
- [ ] Task 4 — Execute the 704-cell / 154-invocation campaign in
  deterministic batches (§15), producing `matrix.json` at the one stable
  campaign root. Exact command shape (repeatable per `--only` batch, all
  batches passing the SAME `--report-dir`):
  ```
  python manage.py qa_storefront_builder_r4 --store-slug rasti-mode-demo --username w4c_qa_owner --port 8765 --browser-channel auto --w4c-all50 --only <key1,key2,...> --report-dir /var/tmp/rastisi_w4c_campaign --settings=shop_core.settings
  ```
  Omit `--only` to run all 50 Templates' base+Theme cells in one invocation
  of the command (internally still 154 separate `run.mjs` process launches,
  §3.2); `--only` is for resuming/re-running a subset against the SAME
  `--report-dir`.
- [ ] Task 5 — Run the visual-distinctness clustering pass (§11) against the
  real Home Desktop+Mobile captures; resolve or escalate any `NEEDS REPAIR`
  finding before proceeding.
- [ ] **Task 6 — Materialize the Home gallery, then handle static Gallery
  staleness separately** (repaired — Round 4, Important 2 + 3):

  **6a. Materialize final Home-gallery evidence (repairs Important 2).**
  Only after Task 4's campaign aggregator (§15) reports
  `total_cells_recorded == 704`, `missing_cells == []`,
  `duplicate_cells == []`: for each of the 50 keys, read
  `{CAMPAIGN_REPORT_ROOT}/w4c-results/base/<key>.json`, confirm its Home
  Desktop and Home Mobile cells both recorded `result: "PASS"`, and copy
  the two staged screenshot files
  (`{CAMPAIGN_REPORT_ROOT}/screenshots/home/<key>_home_desktop.jpg` /
  `..._home_mobile.jpg`) into
  `docs/qa_evidence/storefront_design_engine/phase5/w4_certification/home_gallery/`
  — never re-captured, never sourced from
  `capture_ready_template_previews.py` (§3.8), whose own canonical
  viewport, 1440×1100, is a different, non-substitutable capture. **Final
  evidence gate:** after copying, verify `home_gallery/` contains exactly
  100 files, all 50 keys have both a Desktop and a Mobile file, and every
  copied file's originating cell was `PASS` in `matrix.json` — any FAIL
  here blocks Task 6 from proceeding to 6b (a Home FAIL is a certification
  blocker in its own right, per §4/§11, not a Task-6 concern to paper over).

  **6b. Static Gallery staleness check and, only if needed, a SEPARATE
  refresh server (repairs Important 3).** The `qa_storefront_builder_r4`
  runserver from Task 4 is NOT available here — that command's existing,
  unmodified outer `finally` stops its runserver and restores the SQLite DB
  backup before `handle()` returns (harness inventory §10.B), so by the
  time Task 6 runs, no server from Task 4 is listening on port `8765` or
  any other port. Reusing "port 8765" here would be false, and this plan no
  longer claims it.

  1. For all 50 keys, check `template_preview_service.resolve_real_screenshot(preset)`
     / `preview_input_fingerprint(preset)` (harness inventory §11.6)
     against the currently-stored static Gallery asset. Produce two exact
     lists: `CURRENT_STATIC_PREVIEWS` and `STALE_STATIC_PREVIEWS`.
  2. If `STALE_STATIC_PREVIEWS` is empty: record
     `STATIC GALLERY REFRESH: NOT REQUIRED` in `execution_report.md` and
     stop — do NOT start any server, do NOT run
     `capture_ready_template_previews` at all.
  3. Otherwise, run a SEPARATE, deliberate Gallery-refresh lifecycle — NOT
     the W4C certification server, and never claimed to be:
     ```
     python manage.py seed_ready_template_fashion_demo --settings=shop_core.settings   # ensure fixture current, idempotent
     python manage.py runserver 127.0.0.1:8766 --settings=shop_core.settings &         # dedicated Gallery-refresh port, distinct from 8765
     # wait until http://127.0.0.1:8766/ answers (poll, confirmed ready) before proceeding
     for key in STALE_STATIC_PREVIEWS:
         python manage.py capture_ready_template_previews --base-url http://127.0.0.1:8766 --only <key> --settings=shop_core.settings
     # verify each refreshed asset's new preview_input_fingerprint now matches (no longer stale)
     kill %1   # stop the dedicated port-8766 server in a finally-equivalent cleanup — never leave it running
     ```
  4. Record in `execution_report.md` the exact `STALE_STATIC_PREVIEWS` keys
     refreshed and the (expected, larger) `CURRENT_STATIC_PREVIEWS` list
     left untouched — never blindly refresh all 50.
  5. This refresh step is entirely separate from and CANNOT affect
     `matrix.json` or the campaign's PASS/FAIL result — W4C browser
     certification already completed (6a's gate) before this maintenance
     step runs. Any Gallery-refresh failure here is reported on its own in
     `execution_report.md` and must never rewrite `matrix.json`.
- [ ] Task 7 — Produce all remaining evidence artifacts (§12).
- [ ] Task 8 — Full regression comparison (§14) against the certified W4B
  baseline. Exact commands:
  ```
  python manage.py check --settings=shop_core.settings
  python manage.py makemigrations --check --dry-run --settings=shop_core.settings
  git diff --check
  python manage.py test apps.storefront_builder.tests --settings=shop_core.settings
  ```
- [ ] Task 9 — Architecture/duplication audit (§16) confirming the bounded
  extension introduced nothing beyond what this plan authorized, and
  confirming the Gallery static tree was touched only by Task 6's
  stale-only, explicitly-recorded refresh step.
- [ ] Task 10 — Final clean-status evidence sequence (temp-path capture,
  verify empty, then commit), mirroring W4B's own corrected methodology.
- [ ] Task 11 — Open the unmerged PR (base `feature/phase5-design-expansion`,
  head `feature/phase5-w4c-all50-certification`) and return for Independent
  Architect review.

No task above is started by this document. This document only defines them.
