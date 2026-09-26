# RastiSi Design Studio — real R4 integration: QA evidence

Visual/interaction reference: `RastiSi_Design_Studio.html`
(SHA256 `702f2c4a09faa8f72ac79de59803d1c5e44d1aea1c08a7cf650e795b6bcf5826`).
Entry URL: `/admin-portal/storefront-builder/r4/` (the existing R4 editor route).
Base: `b55e1ac1420e6ec4fa8e4a1b8a7023eb47361cb9`. Branch: `feature/r4-design-studio-ui`.

* `reference/` — the approved reference, captured from its own `?demo=` states.
* `before/` — the R4 editor at the base commit.
* `after/` — the real R4 editor on this branch, against an isolated fixture store
  (no production data, no reseeding of real Stores).

## Architecture (no parallel authority)

* `r4_editor.js` stays the single owner of every operation: the one mutation
  queue (`mutate/`), history (`history/`), publish/discard/reset/switch-template,
  the read-only Design Lab endpoint (`design-lab/`) and the one `#r4PreviewFrame`.
  Exactly five `method: 'POST'` call sites, unchanged in number.
* `r4_studio.js` is presentation only (mode, panel view, tabs, dialogs, gallery
  filter/search, toast, focus, keyboard). Its single `fetch` is a read-only GET of
  the editor page to refresh history/undo/unpublished status. It never writes, never
  uses browser storage, never creates an iframe or renders the storefront.
* Ready Template gallery = the ONE catalog (`build_ready_template_cards`, shared
  with the existing gallery view). Temporary template preview = the existing
  non-destructive live-preview route in the same iframe. Apply = existing
  `switch-template/`.
* Design Lab = existing signed transient candidate + three pure transforms
  (`set_theme`, `reset_to_base`, `return_to_template_dna`) on the existing endpoint.
  Persistence only through the canonical `design_lab.apply_candidate` mutation.
* No model, table, migration, second renderer, second history or template registry.

## Browser journeys (Playwright, Chromium, isolated fixture)

| Journey | Result |
|---|---|
| Section select → inspector (real schema fields, media manager) | PASS |
| Section hide/show, lock/unlock, up/down, duplicate, remove (confirm), move-to-cell | PASS — each one `mutate/` POST |
| Add section (Showcase + full page-legal library) | PASS — one `section.add` |
| Palette / font / style pack → persists after reload | PASS |
| Theme apply / intensity / clear | PASS |
| Undo/redo: toolbar, history dialog, Ctrl+Z, Ctrl+Shift+Z | PASS — `history/` |
| Gallery search/filter → temporary preview → cancel | PASS — zero POSTs, revision unchanged |
| Publish dialog → publish → success dialog after reload | PASS |
| Save error → «بررسی» dialog; version conflict → dialog → reload | PASS |
| Page switch | PASS |
| Lab: start, Random Mix, locks, per-family change, occasion, compare Base/Candidate, template DNA, back to start, apply | PASS — only `design-lab/` until Apply |
| Lab stale candidate (Draft changed in another tab) → rejected, restart | PASS — 409 `stale_candidate`, no write |
| Escape: closes dialog / admin menu, restores focus; never discards, never exits Lab, never confirms | PASS |
| Public view (canonical resolver URL, opened with `noopener`) | PASS — storefront served |
| No document-level horizontal overflow: 1366, 1440, 1920, 1024, 768, 390 | PASS |
| Seven Lab families reachable at every size | PASS |
| Mobile storefront preview with bottom navigation | PASS |
| Raw backend keys in visible Studio text (all journeys) | none |
| Console errors / failed requests (except the intended 409 in the stale test) | none |

## Windows run instructions

```
git remote -v    # this R6 repository uses "origin"
git fetch origin feature/r4-design-studio-ui
git switch feature/r4-design-studio-ui
.venv\Scripts\python manage.py check
.venv\Scripts\python manage.py runserver
```
Open `/admin-portal/storefront-builder/r4/` as a staff user with the
storefront-layout permission. No migration is required.
