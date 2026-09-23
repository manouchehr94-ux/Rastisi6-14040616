# content — Entry Points

```
domain_id: D10
code_baseline: 5883a140
```

## Public HTTP (`apps/content/urls.py`, included at `pages/`)
| Path | View | Purpose |
|---|---|---|
| `pages/newsletter/subscribe/` | `newsletter_subscribe` | create `NewsletterSubscriber` (only public write) |
| `pages/<slug>/` | `page_detail` | render a published `ContentPage` (read; uses `build_universal_storefront_context`) |

## All content CRUD entry points are in `dashboard` (H2)
Content is created/edited/deleted through `apps/dashboard/urls.py` routes → `apps/dashboard/views.py`
functions (see [MUTATION_AUTHORITY](MUTATION_AUTHORITY.md) for the exact `pages/`, `homepage/hero/`,
`homepage/banners/`, `social-links/`, `menus/`, `footer/` route groups and view lines). There is no
content-app write endpoint.

## Context processors (render-time reads)
`apps/content/context_processors.py` injects footer settings, navigation menus, and social links
into the storefront shell (registered in `settings.TEMPLATES`).

## Template tags
`apps/content/templatetags/` — render helpers (destination URLs, media URLs).

## Signals / async / commands
- **No signals.** The only "event" is the MED-001 no-op `transaction.on_commit` cleanup callback in
  `services.py` (which does nothing — O2).
- **No management commands** owned by content.
