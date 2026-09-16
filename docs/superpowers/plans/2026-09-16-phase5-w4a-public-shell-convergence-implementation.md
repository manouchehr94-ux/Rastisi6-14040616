# P5-W4A — Public Storefront Shell Convergence — Implementation Plan

Authority: `docs/superpowers/specs/2026-09-16-phase5-w4a-public-shell-convergence-design.md`
(as repaired). Certified base: `5628d6ee31e177d0b4fa1dddad550f894bca540a`.
Design head: `5d09bf440ab3aad6154457ed017f089447d7c3cb`.

## Production scope (exactly)

- `apps/storefront_builder/services/storefront_context_service.py`
- `apps/customers/views.py`
- `apps/customers/templates/customers/wishlist.html`
- `apps/content/views.py`
- `apps/content/templates/content/page_detail.html`

## Task 1 — shell-only context contract

**Test file:** `apps/storefront_builder/tests/test_w4a_shell_only_context.py`

RED tests (call `build_universal_storefront_context` directly, Python-level,
using a real published/unpublished Draft via `layout_service`):

1. `test_shell_only_published_store_returns_canonical_shell` — publish a
   Store, call with `page_type="wishlist", shell_only=True`. Assert
   `uses_universal_shell is True`, `storefront_version == published version`,
   `storefront_page is None`, `page_type == "wishlist"`,
   `header_variant_template`/`footer_variant_template`/`mobile_bottom_nav_template`
   equal what the SAME Store's real `home`/`cart` call returns (proves same
   projection path), `store_appearance` is not None, `top_level_categories`
   matches `_top_level_categories(store)`, `render_items == []`,
   `rows == []`, `render_containers == []`, `use_container_layout is False`.
2. `test_shell_only_unpublished_store_returns_legacy_fallback` — Store with
   no published layout, `shell_only=True`. Assert the dict is
   IDENTICAL in shape to today's unresolved branch: `uses_universal_shell is False`,
   `storefront_version is None`, `storefront_page is None`,
   `mobile_bottom_nav_template is None`, no `header_variant_template`/
   `footer_variant_template` keys, `render_items == []`.
3. `test_invalid_normal_page_type_preserves_todays_fail_safe` — published
   Store, `page_type="prodcut_detail"` (typo), `shell_only` omitted
   (defaults `False`). Assert unresolved shape — same as #2's shape — proving
   no implicit shell-only inference exists.
4. `test_shell_only_never_touches_a_real_storefront_page` — published Store
   with real Home/Cart `StorefrontPage` rows carrying distinctive section
   content. Call `shell_only=True`. Assert `storefront_page is None` and
   `render_items == []` (not Home's or Cart's items) — prove via
   `django.test.utils.CaptureQueriesContext` or by patching
   `page_resolution_service.resolve_published_page` with
   `unittest.mock.patch` to assert it is never called when `shell_only=True`
   (while `get_published_layout` IS called) — a spy assertion, not output
   coincidence, per the task brief.
5. `test_shell_only_published_sets_request_appearance_version_not_page` —
   published Store, `shell_only=True`: assert
   `request.storefront_appearance_version == published version` and
   `request.storefront_appearance_page is None` (explicit — this is the new
   MANDATORY MINOR contract, §7 of the task brief).
6. `test_normal_page_type_request_side_effects_unchanged` — regression:
   real `page_type=HOME` on a published Store still sets
   `request.storefront_appearance_page` to the resolved `StorefrontPage`
   (today's behavior, unchanged).

**Implementation** (`storefront_context_service.py`):

```python
def build_universal_storefront_context(
    request, store, page_type: str, page_context: dict | None = None,
    *, shell_only: bool = False,
) -> dict:
    if shell_only:
        layout = page_resolution_service.get_published_layout(store)
        if layout is None:
            return _unresolved_context(page_type, store, page_context)
        version = layout.published_version
        return _build_published_shell_context(
            request, store, version, page=None, page_type=page_type,
            page_context=page_context,
        )

    resolved = page_resolution_service.resolve_published_page(store, page_type)
    if not resolved.is_resolved:
        return _unresolved_context(page_type, store, page_context)
    return _build_published_shell_context(
        request, store, resolved.version, page=resolved.page,
        page_type=page_type, page_context=page_context,
    )
```

`_unresolved_context(page_type, store, page_context)` factors today's
existing unresolved-branch body verbatim (no behavior change — pure
extraction, same dict shape, same `hide_empty_public_sections`/
`build_default_render_items`/`top_level_categories` calls).

`_build_published_shell_context(request, store, version, page, page_type, page_context)`
factors today's existing resolved-branch body, with one internal branch on
`page is None`:

- sets `request.storefront_appearance_version = version` (both cases);
- sets `request.storefront_appearance_page = page` (i.e. `None` when
  `page is None` — satisfies the mandatory request-side-effect contract
  without a separate `if`);
- `store_appearance = render_service.resolved_store_appearance_for_request(request, version)`
  (both cases — needs only `version`);
- `header_config = version.effective_header_config()`,
  `footer_config = version.effective_footer_config()` (both cases — needs
  only `version`);
- header/footer/bottom-nav template resolution via
  `render_service.store_appearance_global_renderer_template` (both cases —
  needs only `store_appearance`/`header_config`/`footer_config`);
- `top_level_categories` (both cases);
- if `page is None`: `render_items=[]`, `rows=[]`, `render_containers=[]`,
  `use_container_layout=False` — no call to `build_page_render_items`,
  `hide_empty_public_sections`, `build_container_render_items`, or
  `page.containers.exists()` (all of which require a real `page`);
- else (today's exact behavior): call `render_service.build_page_render_items(page, store, page_context=page_context, store_appearance=store_appearance)`,
  `hide_empty_public_sections`, `group_items_into_rows`,
  `build_container_render_items(page, items)`, `page.containers.exists()`.

`storefront_page` in the returned dict is `page` (so `None` for shell-only).

## Task 2 — Wishlist convergence

**Test file:** `apps/customers/tests/test_wishlist_shell_convergence.py`,
reusing `test_wishlist_store_isolation.py`'s exact fixture shape (two real
`Store` rows, two real verified `StoreDomain` rows, distinct `HTTP_HOST`,
`@override_settings(ALLOWED_HOSTS=...)`, no `request.store` mocking).

RED tests (HTTP-level, `self.client.get(reverse("customers:wishlist"), HTTP_HOST=...)`):

- A/B/C: published Store with a distinctive Header/Footer/Bottom-Nav variant
  selection — assert `resp.templates` includes `storefront_shell.html`'s
  resolved header/footer/bottom-nav partial names (same `resp.templates`
  assertion style as `test_page_shell.py`).
- D: anonymous request — assert the existing login-prompt markup/`can_view=False`
  state still renders, wrapped in canonical chrome.
- E: authenticated, empty wishlist for current Store — existing empty-state
  markup preserved.
- F: authenticated, populated — assert `catalog/partials/product_card.html`
  in `resp.templates` (proves reuse, no new partial).
- G (cross-Store read isolation): one `Customer`, `Wishlist(Product A @ Store A)`
  + `Wishlist(Product B @ Store B)`. `HOST_A` response contains Product A,
  not Product B. `HOST_B` response contains Product B, not Product A.
- H (shell isolation): Store A and Store B published with distinguishably
  different header variants. `HOST_A` Wishlist shows Store A's header
  partial only; `HOST_B` shows Store B's only.
- I (unpublished-Store fallback): Store with no published layout — Wishlist
  still 200s, still shows domain state, `storefront_shell.html`'s
  `{{ block.super }}` path exercised (no crash).

**Implementation:**

`apps/customers/views.py::wishlist_list`:
```python
def wishlist_list(request):
    store = resolve_store_for_storefront(request)
    can_view = _can_use_wishlist(request)
    products = []
    if can_view:
        items = (
            Wishlist.objects.filter(customer=request.user.customer_profile, product__store=store)
            .select_related("product", "product__brand")
            .prefetch_related("product__images")
            .order_by("-created_at")
        )
        products = [item.product for item in items]
    context = {"products": products, "can_view": can_view}
    context.update(
        build_universal_storefront_context(request, store, "wishlist", page_context=context, shell_only=True)
    )
    return render(request, "customers/wishlist.html", context)
```
(local import of `resolve_store_for_storefront` and
`build_universal_storefront_context`, matching this file's existing local-import
style used elsewhere, or a module-level import if that better matches
`apps/customers/views.py`'s actual current import block — verify against
source before writing.)

`apps/customers/templates/customers/wishlist.html`: change
`{% extends "base.html" %}` → `{% extends "storefront_shell.html" %}`. No
other line changes.

## Task 3 — CMS convergence

**Test file:** `apps/content/tests/test_page_shell_convergence.py`, same
two-Store/verified-`StoreDomain` fixture pattern.

RED tests:
- A: published page on a Store with a distinctive header variant — canonical
  Header/Footer/Bottom-Nav present in `resp.templates`.
- B: `page.body`/`page.summary`/`page.title` content present verbatim.
- C/D: `effective_seo_title`/`effective_seo_description` in the rendered
  `<title>`/`<meta name="description">` (extends existing
  `test_seo_title_in_html`-style assertion).
- E: DRAFT page → 404 (regression guard, existing behavior).
- F: Store A's page slug 404s on Store B's host.
- G: Store A's header variant never appears on Store B's page and vice
  versa (two-Store shell-isolation harness).
- H (unpublished-Store fallback): published `ContentPage` on a Store with no
  published UNIVERSAL LAYOUT (these are independent — a Store can have a
  published `ContentPage` without ever having published a Storefront V2
  layout) — page still 200s with domain body, legacy shell fallback.

**Implementation:**

`apps/content/views.py::page_detail`:
```python
def page_detail(request, slug):
    store = resolve_store_for_storefront(request)
    page = get_object_or_404(ContentPage, slug=slug, status=ContentPage.Status.PUBLISHED, store=store)
    context = {"page": page}
    context.update(
        build_universal_storefront_context(request, store, "content_page", page_context=context, shell_only=True)
    )
    return render(request, "content/page_detail.html", context)
```

`apps/content/templates/content/page_detail.html`: change
`{% extends "base.html" %}` → `{% extends "storefront_shell.html" %}`. No
other line changes.

## Verification order

1. Write Task 1 tests → confirm RED (missing `shell_only` kwarg raises
   `TypeError`) → implement → confirm GREEN → run
   `test_page_shell`/`test_render_service` regression → commit.
2. Write Task 2 tests → confirm RED against the Task-1-complete code (view
   still unconverged) → implement → GREEN → run `apps.customers.tests` →
   commit.
3. Write Task 3 tests → confirm RED → implement → GREEN → run
   `apps.content.tests` → commit.
4. Fallback-contract tests folded into Tasks 2/3's own suites (I/H above) —
   no separate task needed.
5. Full regression sweep (§18 of the task brief) → base comparison if any
   unexplained failure → system gates → Browser QA → evidence → self-review
   diff → PR.

## Self-review checklist (before implementation commits)

- [ ] No TODO/TBD placeholders in tests or code.
- [ ] No invented API beyond the approved `shell_only` keyword.
- [ ] No second context owner / second shell.
- [ ] No migration.
- [ ] No implicit unknown-page-type → shell-only inference (test 3 guards this).
- [ ] Tenant-isolation coverage present for both Wishlist and CMS (read +
      shell, both directions).
- [ ] `request.storefront_appearance_version`/`_page` contract covered for
      shell-only, normal, and unpublished cases.
