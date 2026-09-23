# content — Testing

```
domain_id: D10
code_baseline: 5883a140
known_risks: H2
```

## Where content behavior is tested
- **Primarily via `dashboard` view tests** — because content CRUD lives in dashboard views (H2),
  content behavior is exercised through the dashboard content-management view test suite
  (page/hero/banner/social/menu/footer forms, delete, toggle, publish).
- `apps/content/tests/` — destination resolution, media reachability, newsletter subscribe, and
  render-context helpers.

## Coverage gap (INFERRED — the shape of H2)
- **There is no content-domain *service* test suite**, because there is no content write service to
  test. The write logic is covered only indirectly through dashboard view tests. A future content
  service (DR-2) would need its own service-level tests.

## Running (informational; do not modify tests)
Content-relevant tests span `apps/content/tests/` and `apps/dashboard/tests/` (content-view files).
See canonical [`../../canonical/TESTING_MAP.md`](../../canonical/TESTING_MAP.md).
